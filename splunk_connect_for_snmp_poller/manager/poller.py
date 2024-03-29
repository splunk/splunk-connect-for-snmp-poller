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
import copy
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
    create_poller_enricher_entry_key,
    create_poller_scheduler_entry_key,
    parse_inventory_file,
    return_database_id,
    update_enricher_config,
    update_inventory_record,
)
from splunk_connect_for_snmp_poller.manager.profile_matching import (
    assign_profiles_to_device,
    extract_desc,
    get_profiles,
)
from splunk_connect_for_snmp_poller.manager.task_utilities import translate_list_to_oid
from splunk_connect_for_snmp_poller.manager.tasks import snmp_polling
from splunk_connect_for_snmp_poller.manager.validator.inventory_validator import (
    DYNAMIC_PROFILE,
)
from splunk_connect_for_snmp_poller.manager.variables import (
    enricher_existing_varbinds,
    enricher_if_mib,
    enricher_oid_family,
    onetime_if_walk,
)
from splunk_connect_for_snmp_poller.mongo import WalkedHostsRepository
from splunk_connect_for_snmp_poller.utilities import (
    OnetimeFlag,
    file_was_modified,
    multi_key_lookup,
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
        self._enricher_jobs_map = {}
        self._dynamic_jobs = set()
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
        if server_config_modified:
            self._server_config = parse_config_file(self._args.config)
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
            inventory_hosts_with_snmp_data = {}
            new_enricher = self._server_config.get("enricher", {})
            profiles = get_profiles(self._server_config)
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
                ir_host = return_database_id(ir.host)
                inventory_hosts.add(ir_host)
                inventory_hosts_with_snmp_data[ir_host] = copy.deepcopy(ir)
                if ir.profile == DYNAMIC_PROFILE:
                    self.delete_all_dynamic_entries_per_host(ir.host)
                    self.add_device_for_profile_matching(ir)
                    self.check_if_new_host_was_added(entry_key, ir, new_enricher)
                else:
                    if entry_key not in self._jobs_map:
                        self.process_new_job(entry_key, ir, profiles)
                        self.check_if_new_host_was_added(entry_key, ir, new_enricher)
                    else:
                        self.update_schedule_for_changed_conf(entry_key, ir, profiles)

            if server_config_modified:
                if new_enricher != self._old_enricher:
                    self.run_enricher_changed_check(
                        new_enricher, inventory_hosts_with_snmp_data
                    )
            self.clean_job_inventory(inventory_entry_keys, inventory_hosts)

    def check_if_new_host_was_added(self, host_key, inventory_record, new_enricher):
        ir_host = return_database_id(host_key)
        if self._old_enricher != {}:
            if not self._mongo.first_time_walk_was_initiated(ir_host, onetime_if_walk):
                logger.debug(f"New host added: {ir_host}")
                self.__add_enricher_to_a_host(
                    new_enricher, copy.deepcopy(inventory_record), True
                )

    def run_enricher_changed_check(self, new_enricher, inventory_hosts_with_snmp_data):
        logger.info(
            f"Previous enricher: {self._old_enricher} \n New enricher: {new_enricher}"
        )
        if new_enricher == {}:
            logger.debug("Enricher is being deleted from MongoDB")
            self._mongo.delete_all_static_data()
            self._old_enricher = {}
            return
        for inventory_host in inventory_hosts_with_snmp_data.keys():
            self.__add_enricher_to_a_host(
                new_enricher, inventory_hosts_with_snmp_data[inventory_host]
            )
        self._old_enricher = new_enricher

    def __add_enricher_to_a_host(self, current_enricher, ir, new_host=False):
        logger.info("Add enricher to a host")
        old_enricher = {} if new_host else self._old_enricher
        if current_enricher != {}:
            self.process_jobs_for_enricher(current_enricher, ir)
            update_enricher_config(
                old_enricher,
                current_enricher,
                self._mongo,
                ir,
                self._server_config,
                self.__get_splunk_indexes(),
            )

    def delete_all_dynamic_entries_per_host(self, host):
        for entry_key in list(self._jobs_map.keys()):
            if entry_key.split("#")[0] == host and entry_key in self._dynamic_jobs:
                logger.debug("Removing job for %s", entry_key)
                schedule.cancel_job(self._jobs_map.get(entry_key))
                del self._jobs_map[entry_key]
                self._dynamic_jobs.remove(entry_key)

    def delete_all_enricher_entries_per_host(self, host):
        for entry_key in list(self._enricher_jobs_map.keys()):
            if entry_key.split("#")[0] == host:
                logger.debug("Removing job for %s", entry_key)
                schedule.cancel_job(self._enricher_jobs_map.get(entry_key))
                del self._enricher_jobs_map[entry_key]

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
                    self.delete_all_enricher_entries_per_host(db_host_id)
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

    def process_jobs_for_enricher(self, enricher, ir):
        ifmib_structure = multi_key_lookup(
            enricher, (enricher_oid_family, enricher_if_mib, enricher_existing_varbinds)
        )
        for varbind in ifmib_structure:
            ifmib_attr, ttl, = (
                varbind["id"],
                varbind["ttl"],
            )
            ifmib_oid = translate_list_to_oid(["IF-MIB", ifmib_attr])
            db_host = return_database_id(ir.host)
            entry_key = create_poller_enricher_entry_key(db_host, ifmib_attr)
            if entry_key in self._enricher_jobs_map:
                return
            logger.debug("Adding configuration for enricher job %s", entry_key)
            new_ir = update_inventory_record(ir, ifmib_oid, ttl)
            job_reference = schedule.every(int(ttl)).seconds.do(
                snmp_polling,
                new_ir.to_json(),
                self._server_config,
                self.__get_splunk_indexes(),
                None,
                OnetimeFlag.ENRICHER_UPDATE_WALK.value,
            )
            self._enricher_jobs_map[entry_key] = job_reference

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
            self._args.config,
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
            self._args.config,
        )

    def add_device_for_profile_matching(self, device: InventoryRecord):
        self._lock.acquire()
        self._unmatched_devices[device.host] = device
        self._lock.release()

    def process_unmatched_devices_job(self, config_location):
        job_thread = threading.Thread(
            target=self.process_unmatched_devices, args=[config_location]
        )
        job_thread.start()

    def process_unmatched_devices(self, config_location):
        if self._unmatched_devices:
            try:
                server_config = parse_config_file(config_location)
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
                                self._dynamic_jobs.add(entry_key)
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
