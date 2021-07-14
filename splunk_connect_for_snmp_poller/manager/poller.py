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
import os
import time

import schedule

from splunk_connect_for_snmp_poller.manager.tasks import snmp_polling
from splunk_connect_for_snmp_poller.mongo import WalkedHostsRepository
from splunk_connect_for_snmp_poller.manager.validator.inventory_validator import (
    should_process_inventory_line,
    is_valid_inventory_line_from_dict,
)

logger = logging.getLogger(__name__)


class Poller:
    # see https://www.alvestrand.no/objectid/1.3.6.1.html for a better understanding
    universal_base_oid = "1.3.6.1.*"

    def __init__(self, args, server_config):
        self._args = args
        self._server_config = server_config
        self._mod_time = 0
        self._jobs_map = {}
        self._mongo_walked_hosts_coll = WalkedHostsRepository(
            self._server_config["mongo"]
        )

    def get_splunk_indexes(self):
        index = {
            "event_index": self._args.event_index,
            "metric_index": self._args.metric_index,
        }
        return index

    def run(self):
        counter = 0
        while True:
            if counter == 0:
                self.check_inventory()
                counter = int(self._args.refresh_interval)

            schedule.run_pending()
            time.sleep(1)
            counter -= 1

    def should_process_current_line(self, host, version, community, profile, frequency):
        return should_process_inventory_line(
            host
        ) and is_valid_inventory_line_from_dict(
            host, version, community, profile, frequency
        )

    def check_inventory(self):
        inventory_file = self._args.inventory
        splunk_indexes = self.get_splunk_indexes()
        if os.stat(inventory_file, follow_symlinks=True).st_mtime > self._mod_time:
            logger.info("Change in inventory detected, reloading")
            logger.debug(f"[-] Configured the Splunk indexes: {splunk_indexes}")
            self._mod_time = os.stat(inventory_file, follow_symlinks=True).st_mtime

            with open(inventory_file, newline="") as csvfile:
                inventory = csv.DictReader(csvfile, delimiter=",")

                inventory_hosts = set()

                for agent in inventory:
                    host = agent["host"]
                    version = agent["version"]
                    community = agent["community"]
                    profile = agent["profile"]
                    frequency_str = agent["freqinseconds"]
                    if self.should_process_current_line(
                        host, version, community, profile, frequency_str
                    ):
                        entry_key = host + '#' + profile
                        frequency = int(agent["freqinseconds"])

                        if entry_key in inventory_hosts:
                            logger.error(
                                f"{host},{version},{community},{profile},{frequency_str} has duplicated hostname {host} and {profile} in the inventory, cannot use the same profile twice for the same device"
                            )
                            continue

                        inventory_hosts.add(entry_key)

                        # perform one-time walk for the entire tree for each un-walked host
                        self.one_time_walk(
                            host,
                            version,
                            community,
                            Poller.universal_base_oid,
                            self._server_config,
                            splunk_indexes,
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
                                splunk_indexes,
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
                                    splunk_indexes,
                                )
                                or frequency != self._jobs_map.get(entry_key).interval
                            ):
                                self.update_schedule(
                                    community,
                                    frequency,
                                    host,
                                    profile,
                                    version,
                                    self._server_config,
                                    splunk_indexes,
                                )
                for entry_key in list(self._jobs_map):
                    if entry_key not in inventory_hosts:
                        logger.debug(f"Removing job for {entry_key}")
                        schedule.cancel_job(self._jobs_map.get(entry_key))
                        del self._jobs_map[entry_key]

    def update_schedule(
        self,
        community,
        frequency,
        host,
        profile,
        version,
        server_config,
        splunk_indexes,
    ):
        entry_key = host + '#' + profile

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

    def one_time_walk(
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
