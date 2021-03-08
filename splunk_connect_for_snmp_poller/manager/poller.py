import csv
import functools
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
        counter = 0
        while True:
            if counter == 0:
                self.check_inventory()
                counter = int(self._args.refresh_interval)

            schedule.run_pending()
            time.sleep(1)
            counter -= 1

    def check_inventory(self):
        inventory_file = self._args.inventory
        if os.stat(inventory_file).st_mtime > self._mod_time:
            logger.info('Change in inventory detected, reloading')
            self._mod_time = os.stat(inventory_file).st_mtime

            with open(inventory_file, newline='') as csvfile:
                inventory = csv.DictReader(csvfile, delimiter=',')

                all_hosts = set()

                for agent in inventory:
                    try:
                        host = agent['host']
                        # Comment Feature: Skip if the Inventory hostname starts with character '#'
                        if host[:1] != "#":
                            version = agent['version']
                            community = agent['community']
                            profile = agent['profile']
                            frequency = int(agent['freqinseconds'])

                            if version not in ('2c', '3'):
                                logger.debug(f'Unsupported protocol version {version}, skipping')
                                continue

                            all_hosts.add(host)

                            if host not in self._jobs_per_host:
                                logger.debug(f'Adding configuration for host {host}')
                                job_reference = schedule.every(int(frequency)).seconds.do(some_task, host, version, community,
                                                                                          profile, self._server_config)
                                self._jobs_per_host[host] = job_reference
                            else:
                                old_conf = self._jobs_per_host.get(host).job_func.args
                                if old_conf != (host, version, community, profile, self._server_config) or frequency != self._jobs_per_host.get(host).interval:
                                    self.update_schedule(community, frequency, host, profile, version, self._server_config)
                    except ValueError as ve:
                        logger.error(ve)

                for host in list(self._jobs_per_host):
                    if host not in all_hosts:
                        logger.debug(f'Removing host {host}')
                        schedule.cancel_job(self._jobs_per_host.get(host))
                        del self._jobs_per_host[host]

    def update_schedule(self, community, frequency, host, profile, version, server_config):
        logger.debug(f'Updating configuration for host {host}')
        new_job_func = functools.partial(some_task, host, version, community, profile, server_config)
        functools.update_wrapper(new_job_func, some_task)

        self._jobs_per_host.get(host).job_func = new_job_func
        self._jobs_per_host.get(host).interval = frequency
        old_next_run = self._jobs_per_host.get(host).next_run
        self._jobs_per_host.get(host)._schedule_next_run()
        new_next_run = self._jobs_per_host.get(host).next_run

        self._jobs_per_host.get(host).next_run = old_next_run if new_next_run > old_next_run else new_next_run


def some_task(host, version, community, profile, server_config):
    logger.debug(f'Executing some_task for {host} version={version} community={community} profile={profile}')

    snmp_get.delay(host, version, community, profile, server_config)



