import os

import schedule
import time
import csv

#from splunk_connect_for_snmp_poller.manager.celery_client import snmp_get


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
        if os.stat('inventory.csv').st_mtime > self._mod_time:
            self._mod_time = os.stat('inventory.csv').st_mtime

            with open('inventory.csv', newline='') as csvfile:
                inventory = csv.DictReader(csvfile, delimiter=',')

                all_hosts = set()

                for agent in inventory:
                    host = agent['host']
                    version = agent['version']
                    community = agent['community']
                    profile = agent['profile']
                    frequency = agent['freqinseconds']

                    all_hosts.add(agent['host'])

                    if host not in self._jobs_per_host:
                        job_reference = schedule.every(int(frequency)).seconds.do(some_task, host, version, community, profile)
                        self._jobs_per_host[host] = job_reference
                    else:
                        schedule.cancel_job(self._jobs_per_host.get(host))
                        job_reference = schedule.every(int(frequency)).seconds.do(some_task, host, version, community, profile)
                        self._jobs_per_host[host] = job_reference

                for host in list(self._jobs_per_host):
                    if host not in all_hosts:
                        schedule.cancel_job(self._jobs_per_host.get(host))
                        del self._jobs_per_host[host]


def some_task(host, version, community, profile):
    pass
#snmp_get.delay(host, version, community, profile)

