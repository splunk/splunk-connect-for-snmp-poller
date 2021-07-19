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
import csv
import functools
import logging.config
import time

import schedule
from splunk_connect_for_snmp_poller.manager.tasks import snmp_polling
from splunk_connect_for_snmp_poller.manager.validator.inventory_validator import (
    is_valid_inventory_line_from_dict,
    should_process_inventory_line,
)
from splunk_connect_for_snmp_poller.mongo import WalkedHostsRepository
from splunk_connect_for_snmp_poller.utilities import (
    file_was_modified,
    parse_config_file,
)
from splunk_connect_for_snmp_poller.manager.realtime.oid_constant import OidConstant
from splunk_connect_for_snmp_poller.manager.realtime.real_time_data import (
    should_redo_walk,
)

logger = logging.getLogger(__name__)


def _should_process_current_line(host, version, community, profile, frequency):
    return should_process_inventory_line(host) and is_valid_inventory_line_from_dict(
        host, version, community, profile, frequency
    )


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

    def __get_splunk_indexes(self):
        return {
            "event_index": self._args.event_index,
            "metric_index": self._args.metric_index,
        }

    def __get_realtime_task_frequency(self):
        return self._args.realtime_task_frequency

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
            for (
                host,
                version,
                community,
                profile,
                frequency_str,
            ) in _parse_inventory_file(self._args.inventory):
                entry_key = host + "#" + profile
                frequency = int(frequency_str)
                if entry_key in inventory_hosts:
                    logger.error(
                        (
                            f"{host},{version},{community},{profile},{frequency_str} has duplicated "
                            f"hostname {host} and {profile} in the inventory,"
                            f" cannot use the same profile twice for the same device"
                        )
                    )
                    continue

                inventory_hosts.add(entry_key)
                logger.info(
                    f"[-] server_config['profiles']: {self._server_config['profiles']}"
                )
                if entry_key not in self._jobs_map:
                    logger.debug(f"Adding configuration for job {entry_key}")
                    job_reference = schedule.every(int(frequency)).seconds.do(
                        scheduled_task,
                        host,
                        version,
                        community,
                        profile,
                        self._server_config,
                        self.__get_splunk_indexes(),
                    )
                    self._jobs_map[entry_key] = job_reference
                else:
                    old_conf = self._jobs_map.get(entry_key).job_func.args
                    if (
                        old_conf
                        != (
                            host,
                            version,
                            community,
                            profile,
                            self._server_config,
                            self.__get_splunk_indexes(),
                        )
                        or frequency != self._jobs_map.get(entry_key).interval
                    ):
                        self.__update_schedule(
                            community,
                            frequency,
                            host,
                            profile,
                            version,
                            self._server_config,
                            self.__get_splunk_indexes(),
                        )
                for entry_key in list(self._jobs_map):
                    if entry_key not in inventory_hosts:
                        logger.debug(f"Removing job for {entry_key}")
                        schedule.cancel_job(self._jobs_map.get(entry_key))
                        del self._jobs_map[entry_key]

    def __update_schedule(
        self,
        community,
        frequency,
        host,
        profile,
        version,
        server_config,
        splunk_indexes,
    ):
        entry_key = host + "#" + profile

        logger.debug(f"Updating configuration for job {entry_key}")
        new_job_func = functools.partial(
            scheduled_task,
            host,
            version,
            community,
            profile,
            server_config,
            splunk_indexes,
        )
        functools.update_wrapper(new_job_func, scheduled_task)

        self._jobs_map.get(entry_key).job_func = new_job_func
        self._jobs_map.get(entry_key).interval = frequency
        old_next_run = self._jobs_map.get(entry_key).next_run
        self._jobs_map.get(entry_key)._schedule_next_run()
        new_next_run = self._jobs_map.get(entry_key).next_run

        self._jobs_map.get(entry_key).next_run = (
            old_next_run if new_next_run > old_next_run else new_next_run
        )

    def __realtime_walk(
        self, host, version, community, profile, server_config, splunk_indexes
    ):
        logger.debug(
            f"[-]walked flag: {self._mongo_walked_hosts_coll.contains_host(host)}"
        )
        if self._mongo_walked_hosts_coll.contains_host(host) == 0:
            schedule.every().second.do(
                onetime_task,
                host,
                version,
                community,
                profile,
                server_config,
                splunk_indexes,
            )
            self._mongo_walked_hosts_coll.add_host(host)
        else:
            logger.debug(f"[-] One time walk executed for {host}!")

    def __start_realtime_scheduler_task(self):
        schedule.every(self._args.realtime_task_frequency).seconds.do(
            automatic_realtime_task,
            self._mongo_walked_hosts_coll,
            self._args.inventory,
            self.__get_splunk_indexes(),
            self._server_config,
        )


def scheduled_task(host, version, community, profile, server_config, splunk_indexes):
    logger.debug(
        f"Executing scheduled_task for {host} version={version} community={community} profile={profile}"
    )

    snmp_polling.delay(host, version, community, profile, server_config, splunk_indexes)


def onetime_task(host, version, community, profile, server_config, splunk_indexes):
    logger.debug(
        f"Executing onetime_task for {host} version={version} community={community} profile={profile}"
    )

    snmp_polling.delay(
        host,
        version,
        community,
        profile,
        server_config,
        splunk_indexes,
        one_time_flag=True,
    )
    return schedule.CancelJob


def _parse_inventory_file(inventory_file_path):
    with open(inventory_file_path, newline="") as inventory_file:
        for agent in csv.DictReader(inventory_file, delimiter=","):
            host = agent["host"]
            version = agent["version"]
            community = agent["community"]
            profile = agent["profile"]
            frequency_str = agent["freqinseconds"]
            if _should_process_current_line(
                host, version, community, profile, frequency_str
            ):
                yield host, version, community, profile, frequency_str


def _extract_sys_uptime_instance():
    # TODO: add here an actual call to SNMPGET
    return {
        OidConstant.SYS_UP_TIME_INSTANCE: {"value": "123", "type": "TimeTicks"},
    }


def _walk_info(all_walked_hosts_collection, host, current_sys_up_time):
    host_already_walked = all_walked_hosts_collection.contains_host(host) != 0
    should_do_walk = not host_already_walked
    if host_already_walked:
        previous_sys_up_time = all_walked_hosts_collection.real_time_data_for(host)
        should_do_walk = should_redo_walk(previous_sys_up_time, current_sys_up_time)
    return host_already_walked, should_do_walk


def _update_mongo(
    all_walked_hosts_collection, host, host_already_walked, current_sys_up_time
):
    if not host_already_walked:
        all_walked_hosts_collection.add_host(host)
    all_walked_hosts_collection.update_real_time_data_for(host, current_sys_up_time)


"""
This is he realtime task responsible for executing an SNMPWALK when
* we discover an host for the first time, or
* upSysTimeInstance has changed.
"""


def automatic_realtime_task(
    all_walked_hosts_collection, inventory_file_path, splunk_indexes, server_config
):
    for host, version, community, profile, frequency_str in _parse_inventory_file(
        inventory_file_path
    ):
        sys_up_time = _extract_sys_uptime_instance()
        host_already_walked, should_do_walk = _walk_info(
            all_walked_hosts_collection, host, sys_up_time
        )
        if should_do_walk:
            schedule.every().second.do(
                onetime_task,
                host,
                version,
                community,
                profile,
                server_config,
                splunk_indexes,
            )
        _update_mongo(
            all_walked_hosts_collection, host, host_already_walked, sys_up_time
        )
