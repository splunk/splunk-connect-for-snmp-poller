#
# Copyright 2021 Splunk Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import functools
import logging.config
import threading
import time

import schedule
from pysnmp.hlapi import SnmpEngine

from splunk_connect_for_snmp_poller.manager.data.inventory_record import InventoryRecord
from splunk_connect_for_snmp_poller.manager.poller_utilities import (
    automatic_realtime_task,
    create_poller_scheduler_entry_key,
    parse_inventory_file,
    return_database_id,
)
from splunk_connect_for_snmp_poller.manager.profile_matching import get_profiles, \
    assign_profiles_to_device
from splunk_connect_for_snmp_poller.manager.realtime.oid_constant import OidConstant
from splunk_connect_for_snmp_poller.manager.tasks import snmp_polling
from splunk_connect_for_snmp_poller.mongo import WalkedHostsRepository
from splunk_connect_for_snmp_poller.utilities import (
    file_was_modified,
    parse_config_file,
)

logger = logging.getLogger(__name__)


class Poller:
    # see https://www.alvestrand.no/objectid/1.3.6.1.html for a better understanding
    universal_base_oid = "1.3.6.1.*"

    def __init__(self, args, server_config):
        self._args = args
        self._server_config = server_config
        self._inventory_mod_time = 0
        self._config_mod_time = 0
        self._jobs_map = {}
        self._mongo_walked_hosts_coll = WalkedHostsRepository(
            self._server_config["mongo"]
        )
        self._local_snmp_engine = SnmpEngine()
        self._unmatched_devices = []
        self._lock = threading.Lock()

    def __get_splunk_indexes(self):
        return {
            "event_index": self._args.event_index,
            "metric_index": self._args.metric_index,
            "meta_index": self._args.meta_index,
        }

    def run(self):
        self.__start_realtime_scheduler_task()
        counter = 0
        while True:
            if counter == 0:
                self.__check_inventory()
                counter = int(self._args.refresh_interval)

            schedule.run_pending()
            time.sleep(1)
            counter -= 1

    def __check_inventory(self):
        server_config_modified, self._config_mod_time = file_was_modified(
            self._args.config, self._config_mod_time
        )
        if server_config_modified:
            self._server_config = parse_config_file(self._args.config)

        inventory_config_modified, self._inventory_mod_time = file_was_modified(
            self._args.inventory, self._inventory_mod_time
        )

        # update job when either inventory changes or config changes
        if server_config_modified or inventory_config_modified:
            inventory_hosts = set()
            for ir in parse_inventory_file(self._args.inventory):
                entry_key = create_poller_scheduler_entry_key(ir.host, ir.profile)
                if entry_key in inventory_hosts:
                    logger.error(
                        "%s has duplicated hostname %s and %s in the inventory, cannot use the same profile twice for "
                        "the same device",
                        ir.__repr__(),
                        ir.host,
                        ir.profile,
                    )
                    continue
                inventory_hosts.add(entry_key)
                if ir.profile == '*':
                    self.add_device_for_profile_matching(ir)
                else:
                    logger.info(
                        "[-] server_config['profiles']: %s", self._server_config["profiles"]
                    )
                    if entry_key not in self._jobs_map:
                        self.process_new_job(entry_key, ir)
                    else:
                        self.update_schedule_for_changed_conf(entry_key, ir)

            self.clean_job_inventory(inventory_hosts)

    def clean_job_inventory(self, inventory_hosts):
        for entry_key in list(self._jobs_map):
            # TODO handle removal of * profile
            if entry_key not in inventory_hosts:
                logger.debug("Removing job for %s", entry_key)
                schedule.cancel_job(self._jobs_map.get(entry_key))
                db_host_id = return_database_id(entry_key)
                logger.debug("Removing _id %s from mongo database", db_host_id)
                self._mongo_walked_hosts_coll.delete_host(db_host_id)
                del self._jobs_map[entry_key]

    def update_schedule_for_changed_conf(self, entry_key, ir):
        old_conf = self._jobs_map.get(entry_key).job_func.args
        if self.is_conf_changed(entry_key, ir, old_conf):
            self.__update_schedule(ir, self._server_config, self.__get_splunk_indexes())

    def is_conf_changed(self, entry_key, ir, old_conf):
        interval = self._jobs_map.get(entry_key).interval
        config = self._server_config
        indexes = self.__get_splunk_indexes()
        frequency = int(ir.frequency_str)
        return (
            old_conf != (ir.host, ir.version, ir.community, ir.profile, config, indexes)
            or frequency != interval
        )

    def process_new_job(self, entry_key, ir):
        logger.debug("Adding configuration for job %s", entry_key)
        job_reference = schedule.every(int(ir.frequency_str)).seconds.do(
            scheduled_task,
            ir,
            self._server_config,
            self.__get_splunk_indexes(),
        )
        self._jobs_map[entry_key] = job_reference

    def __update_schedule(self, ir, server_config, splunk_indexes):
        entry_key = ir.host + "#" + ir.profile

        logger.debug("Updating configuration for job %s", entry_key)
        new_job_func = functools.partial(
            scheduled_task,
            ir,
            server_config,
            splunk_indexes,
        )
        functools.update_wrapper(new_job_func, scheduled_task)

        self._jobs_map.get(entry_key).job_func = new_job_func
        self._jobs_map.get(entry_key).interval = int(ir.frequency_str)
        old_next_run = self._jobs_map.get(entry_key).next_run
        self._jobs_map.get(entry_key)._schedule_next_run()
        new_next_run = self._jobs_map.get(entry_key).next_run

        self._jobs_map.get(entry_key).next_run = (
            old_next_run if new_next_run > old_next_run else new_next_run
        )

    def __start_realtime_scheduler_task(self):
        # schedule.every().second.do(
        # For debugging purposes better change it to "one second"
        schedule.every(self._args.realtime_task_frequency).seconds.do(
            automatic_realtime_task,
            self._mongo_walked_hosts_coll,
            self._args.inventory,
            self.__get_splunk_indexes(),
            self._server_config,
            self._local_snmp_engine,
        )

        schedule.every(self._args.matching_task_frequency).seconds.do(
            self.process_unmatched_devices,
            self._server_config,
        )

        automatic_realtime_task(self._mongo_walked_hosts_coll, self._args.inventory, self.__get_splunk_indexes(),
                                self._server_config, self._local_snmp_engine)

    def add_device_for_profile_matching(self, device: InventoryRecord):
        self._lock.acquire()
        self._unmatched_devices.append(device)
        self._lock.release()

    def process_unmatched_devices(self, server_config):
        if self._unmatched_devices:
            profiles = get_profiles(server_config)
            self._lock.acquire()
            processed_devices = set()
            for device in self._unmatched_devices:
                realtime_collection = self._mongo_walked_hosts_coll.real_time_data_for(device.host)
                if realtime_collection:
                    sys_descr = realtime_collection[OidConstant.SYS_DESCR]
                    sys_object_id = realtime_collection[OidConstant.SYS_OBJECT_ID]
                    descr = sys_object_id if sys_object_id is not None else sys_descr

                    if descr:
                        assigned_profiles = assign_profiles_to_device(profiles, descr)
                        processed_devices.add(device.host)

                        for profile in assigned_profiles:
                            entry_key = create_poller_scheduler_entry_key(device.host, profile)
                            new_record = InventoryRecord(device.host, device.version, device.community, profile)
                            self.process_new_job(entry_key, new_record)

            self._unmatched_devices = [i for i in self._unmatched_devices if i.host not in processed_devices]
            self._lock.release()


def scheduled_task(ir: InventoryRecord, server_config, splunk_indexes):
    logger.debug("Executing scheduled_task for %s", ir.__repr__())
    snmp_polling.delay(ir.to_json(), server_config, splunk_indexes)
