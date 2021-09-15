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
import asyncio
import os
import threading
import traceback

from asgiref.sync import async_to_sync
from celery.utils.log import get_task_logger
from pysnmp.hlapi import ObjectIdentity, ObjectType, SnmpEngine

from splunk_connect_for_snmp_poller.manager.celery_client import app
from splunk_connect_for_snmp_poller.manager.task_utilities import (
    VarbindCollection,
    build_authData,
    build_contextData,
    is_oid,
    mib_string_handler,
    parse_port,
    snmp_bulk_handler,
    snmp_get_handler,
    walk_handler,
    walk_handler_with_enricher,
)
from splunk_connect_for_snmp_poller.mongo import WalkedHostsRepository

thread_local = threading.local()
logger = get_task_logger(__name__)


def get_shared_snmp_engine():
    if not hasattr(thread_local, "local_snmp_engine"):
        thread_local.local_snmp_engine = SnmpEngine()
        logger.info("Created a single shared instance of an SnmpEngine() object")

    return thread_local.local_snmp_engine


async def get_snmp_data(
    varBinds,
    handler,
    mongo_connection,
    enricher_presence,
    snmp_engine,
    auth_data,
    context_data,
    host,
    port,
    mib_server_url,
    index,
    otel_logs_url,
    otel_metrics_url,
    one_time_flag,
):
    if varBinds:
        try:
            await handler(
                mongo_connection,
                enricher_presence,
                snmp_engine,
                auth_data,
                context_data,
                host,
                port,
                mib_server_url,
                index,
                otel_logs_url,
                otel_metrics_url,
                one_time_flag,
                varBinds,
            )
        except Exception as e:
            logger.error(f"Error happend while calling {handler.__name__}(): {e}")
            traceback.print_exc()


def sort_varbinds(varbind_list: list) -> VarbindCollection:
    """
    This function sorts varbinds based on their final destination.
    We have 2 possible operations to run on snmp:
        1. Get - when varbind is a 3-element list, ex. ['SNMPv2-MIB', 'sysUpTime', 0]
                - when varbind is an element without a '*' as a last element
        2. Bulk - when varbind is an element with a '*' as a last element
                - when varbind is a 2-element list, ex. ['CISCO-FC-MGMT-MIB', 'cfcmPortLcStatsEntry']
    @param varbind_list: list of unsorted varbinds given as parameters to make qquery
    @return: VarbindCollection object with seperate varbinds for walk and bulk
    """
    _tmp_multikey_elements = []
    get_list, bulk_list = [], []
    for varbind in varbind_list:
        if isinstance(varbind, list):
            _tmp_multikey_elements.append(varbind)
        else:
            if varbind[-1] == "*":
                bulk_list.append(ObjectType(ObjectIdentity(varbind[:-2])))
            else:
                get_list.append(ObjectType(ObjectIdentity(varbind)))

    # in case of lists we use mib_string_handler function to divide varbinds on walk/bulk based on number of elements
    casted_multikey_elements = mib_string_handler(_tmp_multikey_elements)
    casted_multikey_elements += VarbindCollection(get=get_list, bulk=bulk_list)
    return casted_multikey_elements


# TODO remove the debugging statement later
@app.task
def snmp_polling(
    host, version, community, profile, server_config, index, one_time_flag=False
):
    async_to_sync(snmp_polling_async)(host, version, community, profile, server_config, index, one_time_flag)

    return f"Executing SNMP Polling for {host} version={version} profile={profile}"


async def snmp_polling_async(
        host, version, community, profile, server_config, index, one_time_flag=False
):
    mib_server_url = os.environ["MIBS_SERVER_URL"]
    otel_logs_url = os.environ["OTEL_SERVER_LOGS_URL"]
    otel_metrics_url = os.environ["OTEL_SERVER_METRICS_URL"]
    host, port = parse_port(host)
    logger.info(f"Using the following MIBS server URL: {mib_server_url}")

    # create one SnmpEngie for snmp_get_handler, walk_handler, mib_string_handler
    snmp_engine = get_shared_snmp_engine()

    # create auth_data depending on SNMP's version
    auth_data = build_authData(version, community, server_config)
    logger.debug(f"==========auth_data=========\n{auth_data}")

    # create context_data for SNMP v3
    context_data = build_contextData(version, community, server_config)
    logger.debug(f"==========context_data=========\n{context_data}")

    mongo_connection = WalkedHostsRepository(server_config["mongo"])
    enricher_presence = True if "enricher" in server_config else False
    static_parameters = [
        snmp_engine,
        auth_data,
        context_data,
        host,
        port,
        mib_server_url,
        index,
        otel_logs_url,
        otel_metrics_url,
        one_time_flag,
    ]
    get_bulk_specific_parameters = [mongo_connection, enricher_presence]

    try:
        # Perform SNNP Polling for string profile in inventory.csv
        if not is_oid(profile):
            logger.info(
                f"Executing SNMP Polling for Varbinds in config.yaml for {host} profile={profile}"
            )
            mib_profile = server_config["profiles"].get(profile, None)
            if mib_profile:
                varBinds = mib_profile.get("varBinds", None)
                # Divide varBinds for WALK/BULK actions
                varbind_collection = sort_varbinds(varBinds)
                logger.info(f"Varbind collection: {varbind_collection}")
                # Perform SNMP BULK
                await get_snmp_data(
                    varbind_collection.bulk,
                    snmp_bulk_handler,
                    *get_bulk_specific_parameters,
                    *static_parameters,
                )
                # Perform SNMP WALK
                await get_snmp_data(
                    varbind_collection.get,
                    snmp_get_handler,
                    *get_bulk_specific_parameters,
                    *static_parameters,
                )
        # Perform SNNP Polling for oid profile in inventory.csv
        else:
            # Perform SNNP WALK for oid end with *
            if profile[-1] == "*":
                logger.info(f"Executing SNMP WALK for {host} profile={profile}")
                if enricher_presence:
                    await walk_handler_with_enricher(
                        profile, server_config, mongo_connection, *static_parameters
                    )
                else:
                    walk_handler(profile, *static_parameters)
            # Perform SNNP GET for an oid
            else:
                logger.info(f"Executing SNMP GET for {host} profile={profile}")
                prepared_profile = [ObjectType(ObjectIdentity(profile))]
                await snmp_get_handler(
                    *get_bulk_specific_parameters, *static_parameters, prepared_profile
                )

    except Exception as e:
        logger.error(
            f"Error happend while executing SNMP polling for {host}, version={version}, profile={profile}: {e}"
        )
