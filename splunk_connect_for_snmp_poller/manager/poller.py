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
import time

import schedule
from pysnmp.hlapi import SnmpEngine
from splunk_connect_for_snmp_poller.manager.poller_utilities import (
    automatic_realtime_task,
    create_poller_scheduler_entry_key,
    parse_inventory_file,
)
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
            for ir in parse_inventory_file(self._args.inventory):
                entry_key = create_poller_scheduler_entry_key(ir.host, ir.profile)
                frequency = int(ir.frequency_str)
                if entry_key in inventory_hosts:
                    logger.error(
                        (
                            f"{ir.host},{ir.version},{ir.community},{ir.profile},{ir.frequency_str} has duplicated "
                            f"hostname {ir.host} and {ir.profile} in the inventory,"
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
                    job_reference = schedule.every(frequency).seconds.do(
                        scheduled_task,
                        ir.host,
                        ir.version,
                        ir.community,
                        ir.profile,
                        self._server_config,
                        self._mongo_walked_hosts_coll,
                        self.__get_splunk_indexes(),
                    )
                    self._jobs_map[entry_key] = job_reference
                else:
                    old_conf = self._jobs_map.get(entry_key).job_func.args
                    if (
                        old_conf
                        != (
                            ir.host,
                            ir.version,
                            ir.community,
                            ir.profile,
                            self._server_config,
                            self.__get_splunk_indexes(),
                        )
                        or frequency != self._jobs_map.get(entry_key).interval
                    ):
                        self.__update_schedule(
                            ir.community,
                            ir.frequency,
                            ir.host,
                            ir.profile,
                            ir.version,
                            self._server_config,
                            self._mongo_walked_hosts_coll,
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
        mongo_connection,
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
            mongo_connection,
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


def scheduled_task(host, version, community, profile, server_config, mongo_connection, splunk_indexes):
    logger.debug(
        f"Executing scheduled_task for {host} version={version} community={community} profile={profile}"
    )

    # snmp_polling(host, version, community, profile, server_config, splunk_indexes)
    snmp_polling.delay(host, version, community, profile, server_config, mongo_connection, splunk_indexes)
    # snmp_polling(host, version, community, profile, server_config, splunk_indexes, mongo_connection)
