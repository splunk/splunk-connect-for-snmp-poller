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
import logging.config

import schedule
from pysnmp.hlapi import ObjectIdentity, ObjectType, UdpTransportTarget, getCmd
from splunk_connect_for_snmp_poller.manager.realtime.oid_constant import (
    OidConstant,
)
from splunk_connect_for_snmp_poller.manager.realtime.real_time_data import (
    should_redo_walk,
)
from splunk_connect_for_snmp_poller.manager.tasks import snmp_polling
from splunk_connect_for_snmp_poller.manager.validator.inventory_validator import (
    is_valid_inventory_line_from_dict,
    should_process_inventory_line,
)

logger = logging.getLogger(__name__)


def _should_process_current_line(host, version, community, profile, frequency):
    return should_process_inventory_line(host) and is_valid_inventory_line_from_dict(
        host, version, community, profile, frequency
    )


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


def parse_inventory_file(inventory_file_path):
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


def _extract_sys_uptime_instance(
    local_snmp_engine, host, version, community, server_config
):
    from splunk_connect_for_snmp_poller.manager.task_utilities import (
        parse_port,
    )
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
        all_walked_hosts_collection.add_host(host)
    all_walked_hosts_collection.update_real_time_data_for(host, current_sys_up_time)


"""
This is he realtime task responsible for executing an SNMPWALK when
* we discover an host for the first time, or
* upSysTimeInstance has changed.
"""


def automatic_realtime_task(
    all_walked_hosts_collection,
    inventory_file_path,
    splunk_indexes,
    server_config,
    local_snmp_engine,
):
    for host, version, community, profile, frequency_str in parse_inventory_file(
        inventory_file_path
    ):
        sys_up_time = _extract_sys_uptime_instance(
            local_snmp_engine, host, version, community, server_config
        )
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


def create_poller_scheduler_entry_key(host, profile):
    return host + "#" + profile
