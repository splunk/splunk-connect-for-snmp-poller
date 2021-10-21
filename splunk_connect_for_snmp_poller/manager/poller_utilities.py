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

from splunk_connect_for_snmp_poller.manager.const import DEFAULT_POLLING_FREQUENCY
from splunk_connect_for_snmp_poller.manager.data.inventory_record import InventoryRecord
from splunk_connect_for_snmp_poller.manager.realtime.oid_constant import OidConstant
from splunk_connect_for_snmp_poller.manager.realtime.real_time_data import (
    should_redo_walk,
)
from splunk_connect_for_snmp_poller.manager.static.interface_mib_utililities import (
    extract_network_interface_data_from_additional_config,
)
from splunk_connect_for_snmp_poller.manager.task_utilities import parse_port
from splunk_connect_for_snmp_poller.manager.tasks import snmp_polling
from splunk_connect_for_snmp_poller.manager.validator.inventory_validator import (
    DYNAMIC_PROFILE,
    is_valid_inventory_line_from_dict,
    should_process_inventory_line,
)
from splunk_connect_for_snmp_poller.manager.variables import (
    enricher_if_mib,
    enricher_oid_family,
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
                    get_frequency(agent, profiles, DEFAULT_POLLING_FREQUENCY)
                    if fetch_frequency and agent["profile"] != DYNAMIC_PROFILE
                    else None,
                )


def get_frequency(agent, profiles, default_frequency):
    frequency = multi_key_lookup(profiles, ("profiles", agent["profile"], "frequency"))
    if frequency:
        return frequency
    logger.debug(
        f'Default frequency={DEFAULT_POLLING_FREQUENCY} was assigned for agent={agent.get("host")}, '
        f'profile={agent["profile"]}'
    )
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


def _walk_info(mongo_collection, host, current_sys_up_time):
    host_already_walked = mongo_collection.contains_host(host) != 0
    should_do_walk = not host_already_walked
    if host_already_walked:
        previous_sys_up_time = mongo_collection.real_time_data_for(host)
        should_do_walk = should_redo_walk(previous_sys_up_time, current_sys_up_time)
    return host_already_walked, should_do_walk


def _update_mongo(mongo_collection, host, host_already_walked, current_sys_up_time):
    if not host_already_walked:
        logger.info("Adding host: %s into Mongo database", host)
        mongo_collection.add_host(host)

    prev_content = mongo_collection.real_time_data_for(host)
    if not prev_content:
        prev_content = {}
    prev_content.update(current_sys_up_time)

    mongo_collection.update_real_time_data_for(host, prev_content)


"""
This is the realtime task responsible for executing an SNMPWALK when
* we discover an host for the first time, or
* upSysTimeInstance has changed.
"""


def automatic_realtime_job(
    mongo_collection,
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
            mongo_collection,
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
    mongo_collection,
    splunk_indexes,
    server_config,
):
    job_thread = threading.Thread(
        target=iterate_through_unwalked_hosts_scheduler,
        args=[
            server_config,
            splunk_indexes,
            mongo_collection,
        ],
    )
    job_thread.start()


def automatic_realtime_task(
    mongo_collection,
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
                mongo_collection, db_host_id, sys_up_time
            )
            if should_do_walk:
                logger.info("Scheduling WALK of full tree")
                inventory_record.profile = OidConstant.UNIVERSAL_BASE_OID
                schedule.every().second.do(
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
                mongo_collection,
                db_host_id,
                host_already_walked,
                sys_up_time,
            )
    except Exception:
        logger.exception("Error during automatic_realtime_task")


def update_enricher_config(
    old_enricher,
    new_enricher,
    mongo,
    profiles,
    inventory_host,
    server_config,
    splunk_indexes,
):
    run_ifmib_walk = is_ifmib_different(old_enricher, new_enricher)
    if run_ifmib_walk:
        _update_enricher_config_with_ifmib(
            profiles, inventory_host, server_config, splunk_indexes
        )
    else:
        _update_enricher_config_for_additional_varbinds(
            old_enricher, new_enricher, mongo, inventory_host.host, server_config
        )


def _update_enricher_config_with_ifmib(
    profiles,
    inventory_host,
    server_config,
    splunk_indexes,
):
    inventory_host.profile = OidConstant.IF_MIB
    schedule.every().second.do(
        onetime_task,
        inventory_host,
        server_config,
        splunk_indexes,
        profiles,
    )


def _update_enricher_config_for_additional_varbinds(
    old_enricher,
    new_enricher,
    mongo,
    inventory_host,
    server_config,
):
    families_to_delete = deleted_oid_families(old_enricher, new_enricher)
    mongo.delete_oidfamilies_from_static_data(inventory_host, families_to_delete)
    additional_enricher_varbinds = modified_oid_families(server_config)
    mongo.update_static_data_for_one(inventory_host, additional_enricher_varbinds)


def is_ifmib_different(old_enricher, new_enricher):
    new_if_mib = multi_key_lookup(new_enricher, (enricher_oid_family, enricher_if_mib))
    old_if_mib = multi_key_lookup(old_enricher, (enricher_oid_family, enricher_if_mib))
    return new_if_mib != old_if_mib


def delete_ifmib(func):
    def function(*args, **kwargs):
        set_of_oid_families_to_modify = func(*args, **kwargs)
        if "IF-MIB" in set_of_oid_families_to_modify:
            if isinstance(set_of_oid_families_to_modify, set):
                set_of_oid_families_to_modify.remove("IF-MIB")
            if isinstance(set_of_oid_families_to_modify, dict):
                set_of_oid_families_to_modify.pop("IF-MIB")
        return set_of_oid_families_to_modify

    return function


@delete_ifmib
def deleted_oid_families(old_enricher, new_enricher):
    old_families = old_enricher.get("oidFamily", {})
    new_families = new_enricher.get("oidFamily", {})
    return set(old_families.keys()) - set(new_families.keys())


@delete_ifmib
def modified_oid_families(server_config):
    additional_enricher_varbinds = (
        extract_network_interface_data_from_additional_config(server_config)
    )
    return additional_enricher_varbinds


def create_poller_scheduler_entry_key(host, profile):
    return host + "#" + profile


def return_database_id(host):
    if "#" in host:
        host = host.split("#")[0]
    _host, _port = parse_port(host)
    return f"{_host}:{_port}"
