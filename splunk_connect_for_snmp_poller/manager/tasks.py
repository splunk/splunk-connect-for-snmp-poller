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
import os
import threading

from asgiref.sync import async_to_sync
from celery.utils.log import get_task_logger
from pysnmp.hlapi import ObjectIdentity, ObjectType, SnmpEngine

from splunk_connect_for_snmp_poller.manager.celery_client import app
from splunk_connect_for_snmp_poller.manager.data.inventory_record import InventoryRecord
from splunk_connect_for_snmp_poller.manager.hec_sender import HecSender
from splunk_connect_for_snmp_poller.manager.realtime.oid_constant import OidConstant
from splunk_connect_for_snmp_poller.manager.task_utilities import (
    OnetimeFlag,
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
    var_binds,
    handler,
    mongo_connection,
    enricher,
    snmp_engine,
    hec_sender,
    auth_data,
    context_data,
    host,
    port,
    mib_server_url,
    index,
    one_time_flag,
    ir,
    additional_metric_fields,
):
    if var_binds:
        try:
            await handler(
                mongo_connection,
                enricher,
                snmp_engine,
                hec_sender,
                auth_data,
                context_data,
                host,
                port,
                mib_server_url,
                index,
                one_time_flag,
                ir,
                additional_metric_fields,
                var_binds,
            )
        except Exception as e:
            logger.exception(f"Error occurred while calling {handler.__name__}(): {e}")


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


@app.task(ignore_result=True)
def snmp_polling(
    ir_json: str,
    server_config,
    index,
    profiles,
    one_time_flag=OnetimeFlag.NOT_A_WALK.value,
):
    ir = InventoryRecord.from_json(ir_json)
    logger.info(f"Got one_time_flag - {one_time_flag} with Ir - {ir.__repr__()}")

    async_to_sync(snmp_polling_async)(ir, server_config, index, profiles, one_time_flag)

    return f"Executing SNMP Polling for {ir.host} version={ir.version} profile={ir.profile}"


async def snmp_polling_async(
    ir: InventoryRecord, server_config, index, profiles, one_time_flag: str
):
    hec_sender = HecSender(
        os.environ["OTEL_SERVER_METRICS_URL"], os.environ["OTEL_SERVER_LOGS_URL"]
    )
    mib_server_url = os.environ["MIBS_SERVER_URL"]
    host, port = parse_port(ir.host)
    logger.debug("Using the following MIBS server URL: %s", mib_server_url)

    # create one SnmpEngie for snmp_get_handler, walk_handler, mib_string_handler
    snmp_engine = get_shared_snmp_engine()

    # create auth_data depending on SNMP's version
    auth_data = build_authData(ir.version, ir.community, server_config)
    logger.debug("auth_data\n%s", auth_data)

    # create context_data for SNMP v3
    context_data = build_contextData(ir.version, ir.community, server_config)
    logger.debug("context_data\n%s", context_data)

    mongo_connection = WalkedHostsRepository(server_config["mongo"])
    additional_metric_fields = server_config.get("additionalMetricField")
    enricher_presence = "enricher" in server_config
    static_parameters = [
        snmp_engine,
        hec_sender,
        auth_data,
        context_data,
        host,
        port,
        mib_server_url,
        index,
        one_time_flag,
        ir,
        additional_metric_fields,
    ]
    get_bulk_specific_parameters = [mongo_connection, enricher_presence]
    try:
        # Perform SNNP Polling for string profile in inventory.csv
        if not is_oid(ir.profile):
            logger.info(
                "Executing SNMP Polling for Varbinds in config.yaml for %s profile=%s",
                host,
                ir.profile,
            )
            mib_profile = profiles["profiles"].get(ir.profile, None)
            if mib_profile:
                var_binds = mib_profile.get("varBinds", None)
                if not var_binds:
                    logger.warning(f"No varBinds specified for profile {ir.profile}")
                    return

                # Divide varBinds for WALK/BULK actions
                varbind_collection = sort_varbinds(var_binds)
                logger.debug(f"Varbind collection: {varbind_collection}")
                # Perform SNMP BULK
                await get_snmp_data(
                    varbind_collection.bulk,
                    snmp_bulk_handler,
                    *get_bulk_specific_parameters,
                    *static_parameters,
                )
                # Perform SNMP GET
                await get_snmp_data(
                    varbind_collection.get,
                    snmp_get_handler,
                    *get_bulk_specific_parameters,
                    *static_parameters,
                )
            else:
                logger.warning(f"No profile {ir.profile} found")
        # Perform SNNP Polling for oid profile in inventory.csv
        else:
            # Perform SNNP WALK for oid end with *
            if ir.profile[-1] == "*":
                logger.info("Executing SNMP WALK for %s profile=%s", host, ir.profile)
                if ir.profile.startswith(OidConstant.IF_MIB[:-2]) or (
                    enricher_presence and one_time_flag == OnetimeFlag.AFTER_FAIL.value
                ):
                    if ir.profile.startswith(OidConstant.IF_MIB):
                        profile = ir.profile
                    else:
                        profile = OidConstant.IF_MIB
                    logger.info(
                        "Executing SNMP WALK for IF-MIB %s profile=%s", host, ir.profile
                    )
                    logger.debug(
                        "Executing SNMP small WALK for %s profile=%s",
                        host,
                        profile,
                    )
                    await walk_handler_with_enricher(
                        profile,
                        server_config,
                        mongo_connection,
                        *static_parameters,
                    )
                if ir.profile == OidConstant.UNIVERSAL_BASE_OID:
                    logger.debug(
                        "Executing SNMP big WALK for %s profile=%s",
                        host,
                        ir.profile,
                    )
                    await walk_handler(ir.profile, mongo_connection, *static_parameters)
            # Perform SNNP GET for an oid
            else:
                logger.info("Executing SNMP GET for %s profile=%s", host, ir.profile)
                prepared_profile = [ObjectType(ObjectIdentity(ir.profile))]
                await snmp_get_handler(
                    *get_bulk_specific_parameters, *static_parameters, prepared_profile  # type: ignore
                )

    except Exception:
        logger.exception(
            f"Error occurred while executing SNMP polling for {host}, version={ir.version}, profile={ir.profile}"
        )
