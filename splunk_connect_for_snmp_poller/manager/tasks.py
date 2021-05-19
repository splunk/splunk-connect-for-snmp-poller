from celery.utils.log import get_task_logger

import os
from splunk_connect_for_snmp_poller.manager.celery_client import app
from splunk_connect_for_snmp_poller.manager.hec_sender import post_data_to_splunk_hec
from splunk_connect_for_snmp_poller.manager.task_utilities import (
    get_handler,
    walk_handler,
    mib_string_handler,
    parse_port,
    build_authData,
    build_contextData,
)
from pysnmp.hlapi import *
import os

import threading

# Used to store a single SnmpEngine() instance for each Celery task
thread_local = threading.local()
logger = get_task_logger(__name__)


def get_shared_snmp_engine():
    if not hasattr(thread_local, "local_snmp_engine"):
        thread_local.local_snmp_engine = SnmpEngine()
        logger.info("Created a single shared instance of an SnmpEngine() object")

    return thread_local.local_snmp_engine


# TODO remove the debugging statement later
@app.task
def snmp_polling(
    host, version, community, profile, server_config, index, one_time_flag=False
):
    mib_server_url = os.environ["MIBS_SERVER_URL"]
    otel_logs_url = os.environ["OTEL_SERVER_LOGS_URL"]
    otel_metrics_url = os.environ["OTEL_SERVER_METRICS_URL"]
    host, port = parse_port(host)
    logger.info(f"Using the following MIBS server URL: {mib_server_url}")

    # create one SnmpEngie for get_handler, walk_handler, mib_string_handler
    snmp_engine = get_shared_snmp_engine()

    # create auth_data depending on SNMP's version
    auth_data = build_authData(version, community, server_config)
    logger.debug(f"==========auth_data=========\n{auth_data}")

    # create context_data for SNMP v3
    context_data = build_contextData(version, community, server_config)
    logger.debug(f"==========context_data=========\n{context_data}")

    try:
        # Perform SNNP Polling for string profile in inventory.csv
        if "." not in profile:
            logger.info(
                f"Executing SNMP Polling for Varbinds in config.yaml for {host} profile={profile}"
            )
            mib_profile = server_config["profiles"].get(profile, None)
            if mib_profile:
                varBinds = mib_profile.get("varBinds", None)
                if varBinds:
                    for varbind in varBinds:
                        # check if the varbind is mib string or oid
                        if isinstance(varbind, list):
                            # Perform SNMP polling for mib string
                            try:
                                mib_index = 1
                                if len(varbind) == 3:
                                    mib_index = varbind[2]
                                mib_string_handler(
                                    snmp_engine,
                                    auth_data,
                                    context_data,
                                    host,
                                    port,
                                    varbind[0],
                                    varbind[1],
                                    mib_index,
                                    mib_server_url,
                                    server_config,
                                    index,
                                    otel_logs_url,
                                    otel_metrics_url,
                                    one_time_flag,
                                )
                            except Exception as e:
                                logger.error(
                                    f"Error happend while calling mib_string_handler(): {e}"
                                )
                        else:
                            # Perform SNMP polling for oid
                            try:
                                if varbind[-1] == "*":
                                    walk_handler(
                                        snmp_engine,
                                        auth_data,
                                        context_data,
                                        host,
                                        port,
                                        varbind,
                                        mib_server_url,
                                        index,
                                        otel_logs_url,
                                        otel_metrics_url,
                                        one_time_flag,
                                    )
                                else:
                                    get_handler(
                                        snmp_engine,
                                        auth_data,
                                        context_data,
                                        host,
                                        port,
                                        varbind,
                                        mib_server_url,
                                        index,
                                        otel_logs_url,
                                        otel_metrics_url,
                                        one_time_flag,
                                    )
                            except Exception as e:
                                logger.error(
                                    f"Invalid format for oid. Error message: {e}"
                                )
        # Perform SNNP Polling for oid profile in inventory.csv
        else:
            # Perform SNNP WALK for oid end with *
            if profile[-1] == "*":
                logger.info(f"Executing SNMP WALK for {host} profile={profile}")
                walk_handler(
                    snmp_engine,
                    auth_data,
                    context_data,
                    host,
                    port,
                    profile,
                    mib_server_url,
                    index,
                    otel_logs_url,
                    otel_metrics_url,
                    one_time_flag,
                )
            # Perform SNNP GET for an oid
            else:
                logger.info(f"Executing SNMP GET for {host} profile={profile}")
                get_handler(
                    snmp_engine,
                    auth_data,
                    context_data,
                    host,
                    port,
                    profile,
                    mib_server_url,
                    index,
                    otel_logs_url,
                    otel_metrics_url,
                    one_time_flag,
                )

        return f"Executing SNMP Polling for {host} version={version} profile={profile}"
    except Exception as e:
        logger.error(
            f"Error happend while executing SNMP polling for {host}, version={version}, profile={profile}: {e}"
        )
