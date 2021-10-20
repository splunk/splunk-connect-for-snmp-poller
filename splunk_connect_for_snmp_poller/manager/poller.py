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
    automatic_onetime_task,
    automatic_realtime_job,
    create_poller_scheduler_entry_key,
    parse_inventory_file,
    return_database_id,
    update_enricher_config,
)
from splunk_connect_for_snmp_poller.manager.profile_matching import (
    assign_profiles_to_device,
    extract_desc,
    get_profiles,
)
from splunk_connect_for_snmp_poller.manager.tasks import snmp_polling
from splunk_connect_for_snmp_poller.manager.validator.inventory_validator import (
    DYNAMIC_PROFILE,
)
from splunk_connect_for_snmp_poller.mongo import WalkedHostsRepository
from splunk_connect_for_snmp_poller.utilities import (
    file_was_modified,
    parse_config_file,
)

logger = logging.getLogger(__name__)


class Poller:
    def __init__(self, args, server_config):
        self._args = args
        self._server_config = server_config
        self._inventory_mod_time = 0
        self._config_mod_time = 0
        self._jobs_map = {}
        self._mongo = WalkedHostsRepository(self._server_config["mongo"])
        self._local_snmp_engine = SnmpEngine()
        self._unmatched_devices = {}
        self._lock = threading.Lock()
        self._force_refresh = False
        self._old_enricher = {}

    def force_inventory_refresh(self):
        self._force_refresh = True

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
                counter = self._args.refresh_interval

            schedule.run_pending()
            time.sleep(1)
            counter -= 1

    def __check_inventory(self):
        server_config_modified, self._config_mod_time = file_was_modified(
            self._args.config, self._config_mod_time
        )
        inventory_config_modified, self._inventory_mod_time = file_was_modified(
            self._args.inventory, self._inventory_mod_time
        )

        # update job when either inventory changes or config changes
        if server_config_modified or inventory_config_modified or self._force_refresh:
            self._force_refresh = False
            logger.info(
                f"Refreshing inventory and config: server_config_modified = {server_config_modified}, "
                f"inventory_config_modified = {inventory_config_modified}, "
                f"force_refresh = {self._force_refresh}"
            )

            # TODO should rethink logic with changed to profiles and oids
            inventory_entry_keys = set()
            inventory_hosts = set()
            profiles = get_profiles(self._server_config)
            if server_config_modified:
                self._server_config = parse_config_file(self._args.config)
                new_enricher = self._server_config.get("enricher", {})
                logger.info(new_enricher)
                if new_enricher != self._old_enricher:
                    logger.info(
                        f"new_enricher: {new_enricher}, self._old_enricher: {self._old_enricher}"
                    )
                    update_enricher_config(
                        self._old_enricher,
                        new_enricher,
                        self._mongo,
                        profiles,
                        self._args.inventory,
                        self._server_config,
                        self.__get_splunk_indexes(),
                    )
                    self._old_enricher = new_enricher
            for ir in parse_inventory_file(self._args.inventory, profiles):
                entry_key = create_poller_scheduler_entry_key(ir.host, ir.profile)
                if entry_key in inventory_entry_keys:
                    logger.error(
                        "%s has duplicated hostname %s and %s in the inventory, cannot use the same profile twice for "
                        "the same device",
                        ir.__repr__(),
                        ir.host,
                        ir.profile,
                    )
                    continue
                inventory_entry_keys.add(entry_key)
                inventory_hosts.add(return_database_id(ir.host))
                if ir.profile == DYNAMIC_PROFILE:
                    self.delete_all_entries_per_host(ir.host)
                    self.add_device_for_profile_matching(ir)
                else:
                    logger.debug(
                        "[-] server_config['profiles']: %s",
                        self._server_config["profiles"],
                    )
                    if entry_key not in self._jobs_map:
                        self.process_new_job(entry_key, ir, profiles)
                    else:
                        self.update_schedule_for_changed_conf(entry_key, ir, profiles)

            self.clean_job_inventory(inventory_entry_keys, inventory_hosts)

    def delete_all_entries_per_host(self, host):
        for entry_key in list(self._jobs_map.keys()):
            if entry_key.split("#")[0] == host:
                schedule.cancel_job(self._jobs_map.get(entry_key))
                del self._jobs_map[entry_key]

    def clean_job_inventory(self, inventory_entry_keys: set, inventory_hosts: set):
        for entry_key in list(self._jobs_map):
            if entry_key not in inventory_entry_keys:
                logger.debug("Removing job for %s", entry_key)
                schedule.cancel_job(self._jobs_map.get(entry_key))
                db_host_id = return_database_id(entry_key)
                if db_host_id not in inventory_hosts:
                    logger.info(
                        "Removing _id %s from mongo database, it is not in used hosts %s",
                        db_host_id,
                        str(inventory_hosts),
                    )
                    self._mongo.delete_host(db_host_id)
                    self._mongo.delete_onetime_walk_result(db_host_id)
                del self._jobs_map[entry_key]

    def update_schedule_for_changed_conf(self, entry_key, ir, profiles):
        old_conf = self._jobs_map.get(entry_key).job_func.args
        if self.is_conf_changed(entry_key, ir, old_conf):
            self.__update_schedule(
                ir, self._server_config, self.__get_splunk_indexes(), profiles
            )

    def is_conf_changed(self, entry_key, ir, old_conf):
        interval = self._jobs_map.get(entry_key).interval
        config = self._server_config
        indexes = self.__get_splunk_indexes()
        frequency = int(ir.frequency_str)
        return (
            old_conf != (ir.host, ir.version, ir.community, ir.profile, config, indexes)
            or frequency != interval
        )

    def process_new_job(self, entry_key, ir, profiles):
        acquired_profiles = profiles.get("profiles")
        if acquired_profiles is not None and ir.profile not in acquired_profiles:
            logger.warning(
                f"Specified profile {ir.profile} for device {ir.host} does not exist"
            )
            return

        logger.debug("Adding configuration for job %s", entry_key)
        job_reference = schedule.every(int(ir.frequency_str)).seconds.do(
            scheduled_task,
            ir,
            self._server_config,
            self.__get_splunk_indexes(),
            profiles,
        )
        self._jobs_map[entry_key] = job_reference

    def __update_schedule(self, ir, server_config, splunk_indexes, profiles):
        entry_key = ir.host + "#" + ir.profile

        logger.debug("Updating configuration for job %s", entry_key)
        new_job_func = functools.partial(
            scheduled_task,
            ir,
            server_config,
            splunk_indexes,
            profiles,
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
            automatic_realtime_job,
            self._mongo,
            self._args.inventory,
            self.__get_splunk_indexes(),
            self._server_config,
            self._local_snmp_engine,
            self.force_inventory_refresh,
            False,
        )

        schedule.every(self._args.matching_task_frequency).seconds.do(
            self.process_unmatched_devices_job,
            self._server_config,
        )

        automatic_realtime_job(
            self._mongo,
            self._args.inventory,
            self.__get_splunk_indexes(),
            self._server_config,
            self._local_snmp_engine,
            self.force_inventory_refresh,
            True,
        )
        schedule.every(self._args.onetime_task_frequency).minutes.do(
            automatic_onetime_task,
            self._mongo,
            self.__get_splunk_indexes(),
            self._server_config,
        )

    def add_device_for_profile_matching(self, device: InventoryRecord):
        self._lock.acquire()
        self._unmatched_devices[device.host] = device
        self._lock.release()

    def process_unmatched_devices_job(self, server_config):
        job_thread = threading.Thread(
            target=self.process_unmatched_devices, args=[server_config]
        )
        job_thread.start()

    def process_unmatched_devices(self, server_config):
        if self._unmatched_devices:
            try:
                profiles = get_profiles(server_config)
                self._lock.acquire()
                processed_devices = set()
                for host, device in self._unmatched_devices.items():
                    realtime_collection = self._mongo.real_time_data_for(
                        return_database_id(host)
                    )
                    if realtime_collection:
                        descr = extract_desc(realtime_collection)

                        if any(descr):
                            assigned_profiles = assign_profiles_to_device(
                                profiles["profiles"], descr, host
                            )
                            processed_devices.add(host)

                            for profile, frequency in assigned_profiles:
                                entry_key = create_poller_scheduler_entry_key(
                                    host, profile
                                )
                                new_record = InventoryRecord(
                                    host,
                                    device.version,
                                    device.community,
                                    profile,
                                    frequency,
                                )
                                self.process_new_job(entry_key, new_record, profiles)
                for d in processed_devices:
                    self._unmatched_devices.pop(d)
            except Exception as e:
                logger.exception(f"Error processing unmatched device {e}")
            finally:
                if self._lock.locked():
                    self._lock.release()


def scheduled_task(ir: InventoryRecord, server_config, splunk_indexes, profiles):
    logger.debug("Executing scheduled_task for %s", ir.__repr__())
    snmp_polling.delay(ir.to_json(), server_config, splunk_indexes, profiles)
