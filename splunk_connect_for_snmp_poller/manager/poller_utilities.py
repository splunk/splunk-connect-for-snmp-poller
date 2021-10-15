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
import json
import logging.config
import threading

import schedule
from pysnmp.hlapi import ObjectIdentity, ObjectType, UdpTransportTarget, getCmd

from splunk_connect_for_snmp_poller.manager.data.inventory_record import InventoryRecord
from splunk_connect_for_snmp_poller.manager.realtime.oid_constant import OidConstant
from splunk_connect_for_snmp_poller.manager.realtime.real_time_data import (
    should_redo_walk,
)
from splunk_connect_for_snmp_poller.manager.task_utilities import parse_port
from splunk_connect_for_snmp_poller.manager.tasks import snmp_polling
from splunk_connect_for_snmp_poller.manager.validator.inventory_validator import (
    is_valid_inventory_line_from_dict,
    should_process_inventory_line,
)
from splunk_connect_for_snmp_poller.utilities import OnetimeFlag, multi_key_lookup

logger = logging.getLogger(__name__)


def _should_process_current_line(inventory_record: dict):
    return should_process_inventory_line(
        inventory_record.get("host")
    ) and is_valid_inventory_line_from_dict(
        inventory_record.get("host"),
        inventory_record.get("version"),
        inventory_record.get("community"),
        inventory_record.get("profile"),
        inventory_record.get("frequency_str"),
    )


def iterate_through_unwalked_hosts_scheduler(
    server_config, splunk_indexes, mongo_connection
):
    logger.debug("Executing iterate_through_unwalked_hosts_scheduler")
    profile = OidConstant.UNIVERSAL_BASE_OID
    unwalked_hosts = mongo_connection.get_all_unwalked_hosts()
    for unwalked_host in unwalked_hosts:
        inventory_record = InventoryRecord(
            unwalked_host["host"],
            unwalked_host["version"],
            unwalked_host["community"],
            profile,
            "60",
        )
        schedule.every().second.do(
            onetime_task,
            inventory_record,
            server_config,
            splunk_indexes,
            json.dumps(OnetimeFlag.AFTER_FAIL),
        )


def onetime_task(
    inventory_record: InventoryRecord,
    server_config,
    splunk_indexes,
    one_time_flag=json.dumps(OnetimeFlag.FIRST_WALK),
):
    logger.debug("Executing onetime_task for %s", inventory_record.__repr__())

    snmp_polling.delay(
        inventory_record.to_json(),
        server_config,
        splunk_indexes,
        None,
        one_time_flag=one_time_flag,
    )
    logger.debug("Cancelling onetime_task for %s", inventory_record.__repr__())
    return schedule.CancelJob


def refresh_inventory(force_inventory_refresh):
    force_inventory_refresh()
    return schedule.CancelJob


def parse_inventory_file(inventory_file_path, profiles, fetch_frequency=True):
    with open(inventory_file_path, newline="") as inventory_file:
        for agent in csv.DictReader(inventory_file, delimiter=","):
            if _should_process_current_line(agent):
                yield InventoryRecord(
                    agent["host"],
                    agent["version"],
                    agent["community"],
                    agent["profile"],
                    get_frequency(agent, profiles, 60) if fetch_frequency else None,
                )


def get_frequency(agent, profiles, default_frequency):
    if "profile" in agent:
        frequency = multi_key_lookup(
            profiles, ("profiles", agent["profile"], "frequency")
        )
        if frequency:
            return frequency
    logger.debug(f'Default frequency was assigned for agent = {agent.get("host")}')
    return default_frequency


def _extract_sys_uptime_instance(
    local_snmp_engine, host, version, community, server_config
):
    from splunk_connect_for_snmp_poller.manager.tasks import (
        build_authData,
        build_contextData,
    )

    auth_data = build_authData(version, community, server_config)
    context_data = build_contextData(version, community, server_config)
    device_hostname, device_port = parse_port(host)
    result = getCmd(
        local_snmp_engine,
        auth_data,
        UdpTransportTarget((device_hostname, device_port)),
        context_data,
        ObjectType(ObjectIdentity(OidConstant.SYS_UP_TIME_INSTANCE)),
    )
    error_indication, error_status, error_index, var_binds = next(result)
    sys_up_time_value = 0
    if not error_indication and not error_status:
        for a, b in var_binds:
            if str(a) == OidConstant.SYS_UP_TIME_INSTANCE:
                # class_name = b.__class__.__name__
                sys_up_time_value = b.prettyPrint()
    return {
        OidConstant.SYS_UP_TIME_INSTANCE: {
            "value": str(sys_up_time_value),
            "type": "TimeTicks",
        },
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
        logger.info("Adding host: %s into Mongo database", host)
        all_walked_hosts_collection.add_host(host)

    prev_content = all_walked_hosts_collection.real_time_data_for(host)
    if not prev_content:
        prev_content = {}
    prev_content.update(current_sys_up_time)

    all_walked_hosts_collection.update_real_time_data_for(host, prev_content)


"""
This is the realtime task responsible for executing an SNMPWALK when
* we discover an host for the first time, or
* upSysTimeInstance has changed.
"""


def automatic_realtime_job(
    all_walked_hosts_collection,
    inventory_file_path,
    splunk_indexes,
    server_config,
    local_snmp_engine,
    force_inventory_refresh,
    initial_walk,
):
    job_thread = threading.Thread(
        target=automatic_realtime_task,
        args=[
            all_walked_hosts_collection,
            inventory_file_path,
            splunk_indexes,
            server_config,
            local_snmp_engine,
            force_inventory_refresh,
            initial_walk,
        ],
    )
    job_thread.start()


def automatic_onetime_task(
    all_walked_hosts_collection,
    splunk_indexes,
    server_config,
):
    job_thread = threading.Thread(
        target=iterate_through_unwalked_hosts_scheduler,
        args=[
            server_config,
            splunk_indexes,
            all_walked_hosts_collection,
        ],
    )
    job_thread.start()


def automatic_realtime_task(
    all_walked_hosts_collection,
    inventory_file_path,
    splunk_indexes,
    server_config,
    local_snmp_engine,
    force_inventory_refresh,
    initial_walk,
):
    try:
        for inventory_record in parse_inventory_file(
            inventory_file_path, profiles=None, fetch_frequency=False
        ):
            db_host_id = return_database_id(inventory_record.host)
            sys_up_time = _extract_sys_uptime_instance(
                local_snmp_engine,
                db_host_id,
                inventory_record.version,
                inventory_record.community,
                server_config,
            )
            host_already_walked, should_do_walk = _walk_info(
                all_walked_hosts_collection, db_host_id, sys_up_time
            )
            if should_do_walk:
                logger.info("Scheduling WALK of full tree")
                inventory_record.profile = OidConstant.UNIVERSAL_BASE_OID
                schedule.every(60).second.do(
                    onetime_task,
                    inventory_record,
                    server_config,
                    splunk_indexes,
                )
                if not initial_walk:
                    # force inventory reloading after 2 min with new walk data
                    schedule.every(2).minutes.do(
                        refresh_inventory, force_inventory_refresh
                    )
            _update_mongo(
                all_walked_hosts_collection,
                db_host_id,
                host_already_walked,
                sys_up_time,
            )
    except Exception as e:
        logger.exception(e)


def create_poller_scheduler_entry_key(host, profile):
    return host + "#" + profile


def return_database_id(host):
    if "#" in host:
        host = host.split("#")[0]
    _host, _port = parse_port(host)
    return f"{_host}:{_port}"
