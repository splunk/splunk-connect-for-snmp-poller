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

from splunk_connect_for_snmp_poller.manager.data.Inventory import Inventory
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

logger = logging.getLogger(__name__)


def parse_inventory(agent):
    return Inventory(agent["host"], agent["version"], agent["community"], agent["profile"], agent["freqinseconds"])


def should_process_current_line(agent: Inventory):
    return should_process_inventory_line(agent.host) and is_valid_inventory_line_from_dict(agent)


class Poller:
    # see https://www.alvestrand.no/objectid/1.3.6.1.html for a better understanding
    universal_base_oid = "1.3.6.1.*"

    def __init__(self, args, server_config):
        self._args = args
        self._server_config = server_config
        self._inventory_mod_time = 0
        self._config_mod_time = 0
        self._jobs_per_host = {}
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

    def check_inventory(self):
        splunk_indexes = self.get_splunk_indexes()

        # check if config was modified
        server_config_modified, self._config_mod_time = file_was_modified(
            self._args.config, self._config_mod_time
        )
        if server_config_modified:
            self._server_config = parse_config_file(self._args.config)

        # check if inventory was modified
        inventory_config_modified, self._inventory_mod_time = file_was_modified(
            self._args.inventory, self._inventory_mod_time
        )

        # update job when either inventory changes or config changes
        if server_config_modified or inventory_config_modified:
            with open(self._args.inventory, newline="") as csvfile:
                inventory = csv.DictReader(csvfile, delimiter=",")

                inventory_hosts = set()

                for agent in inventory:
                    agent = parse_inventory(agent)
                    if should_process_current_line(agent):
                        frequency = int(agent.freqinseconds)

                        if agent.host in inventory_hosts:
                            logger.error(f"{agent.__repr__()} has duplicated hostname "
                                         f"{agent.host} in the inventory, please use profile for multiple OIDs per host")
                            continue

                        inventory_hosts.add(agent.host)

                        logger.info("[-] server_config['profiles']: %s", self._server_config['profiles'])
                        # perform one-time walk for the entire tree for each un-walked host
                        self.one_time_walk(
                            agent,
                            Poller.universal_base_oid,
                            self._server_config,
                            splunk_indexes,
                        )

                        if agent.host not in self._jobs_per_host:
                            logger.debug("Adding configuration for host %s", agent.host)
                            job_reference = schedule.every(int(frequency)).seconds.do(
                                scheduled_task,
                                agent,
                                self._server_config,
                                splunk_indexes,
                                frequency
                            )
                            self._jobs_per_host[agent.host] = job_reference
                        else:
                            old_conf = self._jobs_per_host.get(agent.host).job_func.args
                            if self.is_job_configuration_changed(agent, old_conf, splunk_indexes):
                                self.update_schedule(
                                    agent,
                                    self._server_config,
                                    splunk_indexes
                                )
                for host in list(self._jobs_per_host):
                    if host not in inventory_hosts:
                        logger.debug(f"Removing host {host}")
                        schedule.cancel_job(self._jobs_per_host.get(host))
                        del self._jobs_per_host[host]

    def is_job_configuration_changed(self, agent, old_conf, splunk_indexes):
        return old_conf != (
            agent.host, agent.version, agent.community, agent.profile, self._server_config, splunk_indexes) or int(
            agent.freqinseconds) != self._jobs_per_host.get(agent.host).interval

    def update_schedule(self, agent, server_config, splunk_indexes):
        logger.debug("Updating configuration for host %s", agent.host)
        new_job_func = functools.partial(
            scheduled_task,
            agent.host,
            agent.version,
            agent.community,
            agent.profile,
            server_config,
            splunk_indexes,
        )
        functools.update_wrapper(new_job_func, scheduled_task)

        self._jobs_per_host.get(agent.host).job_func = new_job_func
        self._jobs_per_host.get(agent.host).interval = int(agent.freqinseconds)
        old_next_run = self._jobs_per_host.get(agent.host).next_run
        self._jobs_per_host.get(agent.host)._schedule_next_run()
        new_next_run = self._jobs_per_host.get(agent.host).next_run

        self._jobs_per_host.get(agent.host).next_run = (old_next_run if new_next_run > old_next_run else new_next_run)

    def one_time_walk(self, agent, profile, server_config, splunk_indexes):
        walked_flag = self._mongo_walked_hosts_coll.contains_host(agent.host)
        logger.debug("[-]walked flag: %s", walked_flag)
        if walked_flag == 0:
            schedule.every().second.do(
                onetime_task,
                agent,
                profile,
                server_config,
                splunk_indexes,
            )
            self._mongo_walked_hosts_coll.add_host(agent.host)
        else:
            logger.debug("[-] One time walk executed for %s!", agent.host)


def scheduled_task(agent, server_config, splunk_indexes):
    logger.debug("Executing scheduled_task for %s", agent.__repr__())
    snmp_polling.delay(agent, server_config, splunk_indexes)


def onetime_task(agent, profile, server_config, splunk_indexes):
    logger.debug(f"Executing onetime_task for agent -{agent.__repr__} profile={profile}")

    snmp_polling.delay(agent, profile, server_config, splunk_indexes, one_time_flag=True)
    return schedule.CancelJob
