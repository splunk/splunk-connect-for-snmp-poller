import csv
import functools
import logging.config
import os
import time

import schedule

from splunk_connect_for_snmp_poller.manager.tasks import snmp_polling
from splunk_connect_for_snmp_poller.mongo import WalkedHostsRepository



logger = logging.getLogger(__name__)


class Poller:
    def __init__(self, args, server_config):
        self._args = args
        self._server_config = server_config
        self._mod_time = 0
        self._jobs_per_host = {}
        self._mongo_walked_hosts_coll = WalkedHostsRepository(self._server_config["mongo"])

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
        if os.stat(inventory_file, follow_symlinks=True).st_mtime > self._mod_time:
            logger.info('Change in inventory detected, reloading')
            self._mod_time = os.stat(inventory_file, follow_symlinks=True).st_mtime

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

                            # perform one-time walk for the entire tree for each un-walked host
                            self.one_time_walk(host, version, community, "1.3.6.1.*", self._server_config)

                            if host not in self._jobs_per_host:
                                logger.debug(f'Adding configuration for host {host}')
                                job_reference = schedule.every(int(frequency)).seconds.do(scheduled_task, host, version, community,
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
        new_job_func = functools.partial(scheduled_task, host, version, community, profile, server_config)
        functools.update_wrapper(new_job_func, scheduled_task)

        self._jobs_per_host.get(host).job_func = new_job_func
        self._jobs_per_host.get(host).interval = frequency
        old_next_run = self._jobs_per_host.get(host).next_run
        self._jobs_per_host.get(host)._schedule_next_run()
        new_next_run = self._jobs_per_host.get(host).next_run

        self._jobs_per_host.get(host).next_run = old_next_run if new_next_run > old_next_run else new_next_run

    def one_time_walk(self, host, version, community, profile, server_config):
        logger.debug(f"[-]walked flag: {self._mongo_walked_hosts_coll.contains_host(host)}")
        if self._mongo_walked_hosts_coll.contains_host(host) == 0:
            schedule.every().second.do(onetime_task, host, version, community, profile, server_config)
            self._mongo_walked_hosts_coll.add_host(host)
        else:
            logger.debug(f"[-] One time walk executed for {host}!")


def scheduled_task(host, version, community, profile, server_config):
    logger.debug(f'Executing scheduled_task for {host} version={version} community={community} profile={profile}')

    snmp_polling.delay(host, version, community, profile, server_config)


def onetime_task(host, version, community, profile, server_config):
    logger.debug(f'Executing onetime_task for {host} version={version} community={community} profile={profile}')

    snmp_polling.delay(host, version, community, profile, server_config, one_time_flag=True)
    return schedule.CancelJob