import csv
import logging.config
import os
import time

import schedule

from splunk_connect_for_snmp_poller.manager.tasks import snmp_get

logger = logging.getLogger(__name__)


class Poller:
    def __init__(self, args, server_config):
        self._args = args
        self._server_config = server_config
        self._mod_time = 0
        self._jobs_per_host = {}

    def run(self):

        while True:
            self.check_inventory()
            schedule.run_pending()
            time.sleep(1)

    def check_inventory(self):
        inventory_file = self._args.inventory
        if os.stat(inventory_file).st_mtime > self._mod_time:
            logger.info('Change in inventory detected, reloading')
            self._mod_time = os.stat(inventory_file).st_mtime

            with open(inventory_file, newline='') as csvfile:
                inventory = csv.DictReader(csvfile, delimiter=',')

                all_hosts = set()

                for agent in inventory:
                    host = agent['host']
                    version = agent['version']
                    community = agent['community']
                    profile = agent['profile']
                    frequency = agent['freqinseconds']

                    if version not in ('2c', '3'):
                        logger.debug(f'Unsupported protocol version {version}, skipping')
                        continue

                    all_hosts.add(agent['host'])

                    if host not in self._jobs_per_host:
                        job_reference = schedule.every(int(frequency)).seconds.do(some_task, host, version, community,
                                                                                  profile)
                        self._jobs_per_host[host] = job_reference
                    else:
                        logger.debug(f'Updating configuration for host {host}')
                        old_conf = self._jobs_per_host.get(host).job_func.args
                        if old_conf != (host, version, community, profile):
                            schedule.cancel_job(self._jobs_per_host.get(host))
                            job_reference = schedule.every(int(frequency)).seconds.do(some_task, host, version,
                                                                                      community,
                                                                                      profile)
                            self._jobs_per_host[host] = job_reference

                for host in list(self._jobs_per_host):
                    if host not in all_hosts:
                        schedule.cancel_job(self._jobs_per_host.get(host))
                        logger.debug(f'Removing host {host}')
                        del self._jobs_per_host[host]


def some_task(host, version, community, profile):
    snmp_get.delay(host, version, community, profile)
