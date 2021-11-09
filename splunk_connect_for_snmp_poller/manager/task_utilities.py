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
import json
import os
import re
from collections import namedtuple
from typing import Tuple

from celery.utils.log import get_task_logger
from pysnmp.hlapi import (
    CommunityData,
    ContextData,
    UdpTransportTarget,
    UsmUserData,
    bulkCmd,
    getCmd,
    nextCmd,
)
from pysnmp.proto import rfc1902
from pysnmp.smi import builder, compiler, view
from pysnmp.smi.rfc1902 import ObjectIdentity, ObjectType

from splunk_connect_for_snmp_poller.manager.const import (
    AuthProtocolMap,
    PrivProtocolMap,
)
from splunk_connect_for_snmp_poller.manager.hec_sender import post_data_to_splunk_hec
from splunk_connect_for_snmp_poller.manager.mib_server_client import get_translation
from splunk_connect_for_snmp_poller.manager.realtime.interface_mib import InterfaceMib
from splunk_connect_for_snmp_poller.manager.realtime.oid_constant import OidConstant
from splunk_connect_for_snmp_poller.manager.static.interface_mib_utililities import (
    extract_network_interface_data_from_additional_config,
    extract_network_interface_data_from_walk,
)
from splunk_connect_for_snmp_poller.manager.static.mib_enricher import MibEnricher
from splunk_connect_for_snmp_poller.manager.variables import onetime_if_walk
from splunk_connect_for_snmp_poller.utilities import OnetimeFlag

logger = get_task_logger(__name__)


class VarbindCollection(namedtuple("VarbindCollection", "get, bulk")):
    def __add__(self, other):
        return VarbindCollection(bulk=self.bulk + other.bulk, get=self.get + other.get)


# TODO analyze the code here:
# https://github.com/etingof/pysnmp/blob/becd15c79c9a6b5696928ecd50bf5cca8b1770a1/examples/hlapi/v3arch/asyncore/manager/cmdgen/pull-mibs-from-multiple-agents-at-once-over-ipv4-and-ipv6.py#L57
# to compare the performance between the runDispatcher() and the current getCmd()/nextCmd() .

oids_to_store = {OidConstant.SYS_DESCR, OidConstant.SYS_OBJECT_ID}


def is_metric_data(value):
    """
    Check the condition to see if the varBinds belongs to metric data.
     - if mib value is int/float
    @param value: str
    @return: boolean
    """
    # check if the mib value is float
    try:
        float(value)
        return True
    except ValueError:
        return False


def get_translated_string(
    mib_server_url, var_binds, return_multimetric=False, force_event=False
):
    """
    Get the translated/formatted var_binds string depending on whether the var_binds is an event or metric
    Note: if it failed to get translation, return the the original var_binds
    @return result: formated string ready to be sent to Splunk HEC
    @return is_metric: boolean, metric data flag
    """
    logger.debug(f"Getting translation for the following var_binds: {var_binds}")
    is_metric, result = result_without_translation(var_binds, return_multimetric)
    is_metric = False if force_event else is_metric
    original_varbinds = is_metric, result
    # Override the var_binds string with translated var_binds string
    try:
        data_format = _get_data_format(is_metric, return_multimetric)
        result = get_translation(var_binds, mib_server_url, data_format)
        if data_format == "MULTIMETRIC":
            result = json.loads(result)["metric"]
            logger.debug(f"multimetric result\n{result}")
        # TODO double check the result to handle the edge case,
        # where the value of an metric data was translated from int to string
        if "metric_name" in result:
            result_dict = json.loads(result)
            _value = result_dict.get("_value", None)
            logger.debug(f"metric value\n{_value}")
            if not is_metric_data(_value):
                is_metric = False
                data_format = _get_data_format(is_metric, return_multimetric)
                result = get_translation(var_binds, mib_server_url, data_format)
    except Exception:
        logger.exception("Could not perform translation. Returning original var_binds")
        return original_varbinds
    logger.debug(f"final result -- metric: {is_metric}\n{result}")
    return result, is_metric


def result_without_translation(var_binds, return_multimetric):
    # Get Original var_binds as backup in case the mib-server is unreachable
    for name, val in var_binds:
        # Original oid
        # TODO Discuss: should we return the original oid
        # if the mib server is unreachable
        # should we format it align with the format of the translated one
        # result = "{} = {}".format(name.prettyPrint(), val.prettyPrint())
        # check if this is metric data
        is_metric = is_metric_data(val.prettyPrint())
        if is_metric:
            result = {
                # Prefix the metric for ux in analytics workspace
                # Splunk uses . rather than :: for hierarchy.
                # if the metric name contains a . replace with _
                "metric_name": f'sc4snmp.{name.prettyPrint().replace(".", "_").replace("::", ".")}',
                "_value": val.prettyPrint(),
            }
            result = json.dumps(result)
        else:
            if return_multimetric:
                metric_content_dict = {
                    name.prettyPrint(): val.prettyPrint(),
                    InterfaceMib.METRIC_NAME_KEY: name.prettyPrint(),
                }

                metric_content = json.dumps(metric_content_dict)

                non_metric_content = '{oid}="{value}"'.format(
                    oid=name.prettyPrint(), value=val.prettyPrint()
                )

                result_dict = {
                    "metric": metric_content,
                    "non_metric": non_metric_content,
                    "metric_name": name.prettyPrint(),
                }

                result = json.dumps(result_dict)
            else:
                result = '{oid}="{value}"'.format(
                    oid=name.prettyPrint(), value=val.prettyPrint()
                )
        logger.debug("Our result is_metric - %s and string - %s", is_metric, result)
    return is_metric, result


def _get_data_format(is_metric: bool, return_multimetric: bool):
    # if is_metric is true, return_multimetric doesn't matter
    if is_metric:
        return "METRIC"
    return "MULTIMETRIC" if return_multimetric else "TEXT"


def mib_string_handler(mib_list: list) -> VarbindCollection:
    """
    Perform the SNMP Get for mib-name/string, where mib string is a list
    1) case 1: with mib index - consider it as a single oid -> snmpget
    e.g. ['SNMPv2-MIB', 'sysUpTime',0] (syntax -> [<mib_file_name>, <mib_name/string>, <min_index>])

    2) case 2: without mib index - consider it as a oid with * -> snmpbulkwalk
    . ['SNMPv2-MIB', 'sysORUpTime'] (syntax -> [<mib_file_name>, <mib_name/string>)
    """
    if not mib_list:
        return VarbindCollection(get=[], bulk=[])
    get_list, bulk_list = [], []
    mibBuilder = builder.MibBuilder()
    mibViewController = view.MibViewController(mibBuilder)
    config = {"sources": [os.environ["MIBS_FILES_URL"]]}
    compiler.addMibCompiler(mibBuilder, **config)
    for mib_string in mib_list:
        try:
            if len(mib_string) == 3:
                # convert mib string to oid
                oid = ObjectIdentity(
                    mib_string[0], mib_string[1], mib_string[2]
                ).resolveWithMib(mibViewController)
                logger.debug(f"[-] oid: {oid}")
                get_list.append(ObjectType(oid))

            elif len(mib_string) == 2:
                # convert mib string to oid
                oid = ObjectIdentity(mib_string[0], mib_string[1]).resolveWithMib(
                    mibViewController
                )
                logger.debug(f"[-] oid: {oid}")
                bulk_list.append(ObjectType(oid))

            else:
                raise Exception(
                    f"Invalid mib string - {mib_string}."
                    f"\nPlease provide a valid mib string in the correct format. "
                    f"Learn more about the format at https://bit.ly/3qtqzQc"
                )
        except Exception as e:
            logger.error(
                f"Error happened while polling for mib string: {mib_string}: {e}"
            )
    return VarbindCollection(get=get_list, bulk=bulk_list)


def snmp_get_handler(
    mongo_connection,
    enricher_presence,
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
):
    """
    Perform the SNMP Get for an oid,
    e.g. 1.3.6.1.2.1.1.9.1.2.1,
    which queries the info correlated to this specific oid
    """
    errorIndication, errorStatus, errorIndex, varBinds = next(
        getCmd(
            snmp_engine,
            auth_data,
            UdpTransportTarget((host, port)),
            context_data,
            *var_binds,
        )
    )
    if not _any_failure_happened(errorIndication, errorStatus, errorIndex, varBinds):
        mib_enricher, return_multimetric = _enrich_response(
            mongo_connection, enricher_presence, f"{host}:{port}"
        )
        for varbind in varBinds:
            result, is_metric = get_translated_string(
                mib_server_url, [varbind], return_multimetric
            )
            post_data_to_splunk_hec(
                hec_sender,
                host,
                result,
                is_metric,
                index,
                ir,
                additional_metric_fields,
                one_time_flag=OnetimeFlag.is_a_walk(one_time_flag),
                mib_enricher=mib_enricher,
            )
    else:
        is_error, result = prepare_error_message(
            errorIndication, errorStatus, errorIndex, varBinds
        )
        if is_error:
            post_data_to_splunk_hec(
                hec_sender,
                host,
                result,
                False,  # fail during bulk so sending to event index
                index,
                ir,
                additional_metric_fields,
                one_time_flag=OnetimeFlag.is_a_walk(one_time_flag),
                is_error=is_error,
            )


def _enrich_response(mongo_connection, enricher_presence, hostname):
    if not enricher_presence:
        return None, False
    processed_data = mongo_connection.static_data_for(hostname)
    if processed_data:
        mib_enricher = MibEnricher(processed_data)
        return_multimetric = True
    else:
        mib_enricher = None
        return_multimetric = False
    return mib_enricher, return_multimetric


def _any_failure_happened(
    error_indication, error_status, error_index, var_binds: list
) -> bool:
    """
    This function checks if any failure happened during GET or BULK operation.
    @param error_indication:
    @param error_status:
    @param error_index: index of varbind where error appeared
    @param var_binds: list of varbinds
    @return: if any failure happened
    """
    if error_indication:
        result = f"error: {error_indication}"
        logger.error(result)
    elif error_status:
        result = "error: {} at {}".format(
            error_status.prettyPrint(),
            error_index and var_binds[int(error_index) - 1][0] or "?",
        )
        logger.error(result)
    else:
        return False
    return True


def _any_walk_failure_happened(
    hec_sender,
    error_indication,
    error_status,
    error_index,
    host,
    index,
    one_time_flag,
    is_metric,
    ir,
    additional_metric_fields,
    var_binds,
):
    is_error, result = prepare_error_message(
        error_indication, error_status, error_index, var_binds
    )

    if is_error:
        post_data_to_splunk_hec(
            hec_sender,
            host,
            result,
            is_metric,
            index,
            ir,
            additional_metric_fields,
            one_time_flag=one_time_flag,
            is_error=is_error,
        )

    return is_error


def prepare_error_message(
    error_indication, error_status, error_index, var_binds
) -> Tuple[bool, str]:
    result = ""
    is_error = False
    if error_indication:
        logger.debug(f"Result with error indication - {result}")
        result = f"error: {error_indication}"
        is_error = True
    elif error_status:
        result = "error: {} at {}".format(
            error_status.prettyPrint(),
            error_index and var_binds[int(error_index) - 1][0] or "?",
        )
        is_error = True
    return is_error, result


def snmp_bulk_handler(
    mongo_connection,
    enricher_presence,
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
):
    """
    Perform the SNMP Bulk for an array of oids
    """
    g = bulkCmd(
        snmp_engine,
        auth_data,
        UdpTransportTarget((host, port)),
        context_data,
        0,
        50,
        *var_binds,
        lexicographicMode=False,
    )
    for (errorIndication, errorStatus, errorIndex, var_binds) in g:
        if not _any_failure_happened(
            errorIndication, errorStatus, errorIndex, var_binds
        ):
            mib_enricher, return_multimetric = _enrich_response(
                mongo_connection, enricher_presence, f"{host}:{port}"
            )
            # Bulk operation returns array of var_binds
            for varbind in var_binds:
                logger.debug(f"Bulk returned this varbind: {var_binds}")
                result, is_metric = get_translated_string(
                    mib_server_url, [varbind], return_multimetric
                )
                post_data_to_splunk_hec(
                    hec_sender,
                    host,
                    result,
                    is_metric,
                    index,
                    ir,
                    additional_metric_fields,
                    one_time_flag=OnetimeFlag.is_a_walk(one_time_flag),
                    mib_enricher=mib_enricher,
                )
        else:
            is_error, result = prepare_error_message(
                errorIndication, errorStatus, errorIndex, var_binds
            )
            if is_error:
                post_data_to_splunk_hec(
                    hec_sender,
                    host,
                    result,
                    False,  # fail during bulk so sending to event index
                    index,
                    ir,
                    additional_metric_fields,
                    one_time_flag=OnetimeFlag.is_a_walk(one_time_flag),
                    is_error=is_error,
                )
            break


def walk_handler(
    profile,
    mongo_connection,
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
    """
    Perform the SNMP Walk for oid end with *,
    e.g. 1.3.6.1.2.1.1.9.*,
    which queries the infos correlated to all the oids that underneath the prefix before the *, e.g. 1.3.6.1.2.1.1.9
    """
    error_in_one_time_walk = False
    for (errorIndication, errorStatus, errorIndex, var_binds) in nextCmd(
        snmp_engine,
        auth_data,
        UdpTransportTarget((host, port)),
        context_data,
        ObjectType(ObjectIdentity(profile[:-2])),
        lexicographicMode=False,
    ):
        is_metric = False
        extract_data_to_mongo(host, port, mongo_connection, var_binds)
        if _any_walk_failure_happened(
            hec_sender,
            errorIndication,
            errorStatus,
            errorIndex,
            host,
            index,
            OnetimeFlag.is_a_walk(one_time_flag),
            is_metric,
            ir,
            additional_metric_fields,
            var_binds,
        ):
            if OnetimeFlag.is_a_walk(one_time_flag):
                error_in_one_time_walk = True
            break
        else:
            result, is_metric = get_translated_string(
                mib_server_url, var_binds, force_event=True
            )
            post_data_to_splunk_hec(
                hec_sender,
                host,
                result,
                False,
                index,
                ir,
                additional_metric_fields,
                one_time_flag=OnetimeFlag.is_a_walk(one_time_flag),
            )
    if OnetimeFlag.is_a_walk(one_time_flag):
        process_one_time_flag(
            one_time_flag,
            error_in_one_time_walk,
            mongo_connection,
            f"{host}:{port}",
            ir,
        )
    logger.info(f"Walk finished for {host} profile={profile}")


def extract_data_to_mongo(host, port, mongo_connection, var_binds):
    oid = str(var_binds[0][0].getOid())
    val = str(var_binds[0][1])
    if oid in oids_to_store:
        host_id = "{host}:{port}".format(host=host, port=port)

        prev_content = mongo_connection.real_time_data_for(host_id)
        if not prev_content:
            prev_content = {}
        prev_content[oid] = {
            "value": val,
            "type": "str",
        }

        mongo_connection.update_real_time_data_for(host_id, prev_content)


def process_one_time_flag(
    one_time_flag, error_in_one_time_walk, mongo_connection, host, ir
):
    logger.info(
        f"process_one_time_flag {one_time_flag} {error_in_one_time_walk} {host}"
    )
    if one_time_flag == OnetimeFlag.FIRST_WALK.value and error_in_one_time_walk:
        mongo_connection.add_onetime_walk_result(host, ir.version, ir.community)
    if one_time_flag == OnetimeFlag.AFTER_FAIL.value and not error_in_one_time_walk:
        mongo_connection.delete_onetime_walk_result(host)


def walk_handler_with_enricher(
    profile,
    enricher,
    mongo_connection,
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
    """
    Perform the SNMP Walk for oid end with *,
    e.g. 1.3.6.1.2.1.1.9.*,
    which queries the infos correlated to all the oids that underneath the prefix before the *, e.g. 1.3.6.1.2.1.1.9
    """
    merged_result = []
    merged_result_metric = []
    merged_result_non_metric = []
    for (errorIndication, errorStatus, errorIndex, var_binds) in nextCmd(
        snmp_engine,
        auth_data,
        UdpTransportTarget((host, port)),
        context_data,
        ObjectType(ObjectIdentity(profile[:-2])),
        lexicographicMode=False,
    ):
        is_metric = False
        if _any_walk_failure_happened(
            hec_sender,
            errorIndication,
            errorStatus,
            errorIndex,
            host,
            index,
            OnetimeFlag.is_a_walk(one_time_flag),
            is_metric,
            ir,
            additional_metric_fields,
            var_binds,
        ):
            break
        else:
            result, is_metric = get_translated_string(mib_server_url, var_binds, True)
            new_result = _sort_walk_data(
                is_metric,
                merged_result_metric,
                merged_result_non_metric,
                merged_result,
                result,
            )
            post_data_to_splunk_hec(
                hec_sender,
                host,
                new_result,
                is_metric,
                index,
                ir,
                additional_metric_fields,
                one_time_flag=OnetimeFlag.is_a_walk(one_time_flag),
            )

    logger.info(f"Walk finished for {host} profile={profile}")
    if merged_result:
        mongo_connection.update_walked_host(f"{host}:{port}", {onetime_if_walk: True})
    processed_result = extract_network_interface_data_from_walk(enricher, merged_result)
    additional_enricher_varbinds = (
        extract_network_interface_data_from_additional_config(enricher)
    )
    mongo_connection.update_mib_static_data_for(
        f"{host}:{port}", processed_result, additional_enricher_varbinds
    )


def _sort_walk_data(
    is_metric: bool,
    merged_result_metric: list,
    merged_result_non_metric: list,
    merged_result: list,
    varbind,
):
    """
    In WALK operation we can have three scenarios:
        1. mongo db is empty and we want to insert enricher mapping into it
        2. mongo db already has some data and we just need to use it
        3. we don't have any enricher given in config so we're not adding any extra dimensions
    Because of different structure of metric/non-metric data we need to divide varbinds on 3 categories.
    @param is_metric: is current varbind metric
    @param merged_result_metric: list containing metric varbinds
    @param merged_result_non_metric: list containing non-metric varbinds
    @param merged_result: list containing metric varbinds and metric versions of non-metric varbinds (necessary for 1st
    scenario.
    @param varbind: current varbind
    @return:
    """
    if is_metric:
        merged_result_metric.append(varbind)
        result_to_send_to_hec = varbind
        merged_result.append(json.loads(varbind))
    else:
        merged_result_non_metric.append(varbind)
        result_dict = json.loads(varbind)
        metric_part = result_dict["metric"]
        if isinstance(metric_part, str):
            metric_part = json.loads(metric_part)
        merged_result.append(metric_part)
        result_to_send_to_hec = result_dict["non_metric"]
    return result_to_send_to_hec


def parse_port(host):
    """
    @params host: host filed in inventory.csv. e.g 10.202.12.56, 127.0.0.1:1162
    @return host, port
    """
    if ":" in host:
        tmp = host.split(":")
        host = tmp[0]
        port = tmp[1]
    else:
        port = 161
    return host, port


def build_authData(version, community, server_config):
    """
    create authData (CommunityData or UsmUserData) instance based on the SNMP's version
    @params version: str, "1" | "2c" | "3"
    @params community:
        for v1/v2c: str, community string/community name, e.g. "public"
        for v3: str, userName
    @params server_config: dict of config.yaml
        for v3 to lookup authKey/privKey using userName
    @return authData class instance
        for v1/v2c: CommunityData class instance
        for v3: UsmUserData class instance
    reference: https://github.com/etingof/pysnmp/blob/master/pysnmp/hlapi/v3arch/auth.py
    """
    if version == "3":
        try:
            # Essential params for SNMP v3
            # UsmUserData(userName, authKey=None, privKey=None)
            userName = community
            authKey = None
            privKey = None
            authProtocol = None
            privProtocol = None
            securityEngineId = None
            securityName = None
            authKeyType = 0
            privKeyType = 0

            if server_config["usernames"].get(userName, None):
                authKey = server_config["usernames"][userName].get("authKey", None)
                privKey = server_config["usernames"][userName].get("privKey", None)

                authProtocol = server_config["usernames"][userName].get(
                    "authProtocol", None
                )
                if authProtocol:
                    authProtocol = AuthProtocolMap.get(authProtocol.upper(), "NONE")
                privProtocol = server_config["usernames"][userName].get(
                    "privProtocol", None
                )
                if privProtocol:
                    privProtocol = PrivProtocolMap.get(privProtocol.upper(), "NONE")
                securityEngineId = server_config["usernames"][userName].get(
                    "securityEngineId", None
                )
                if securityEngineId:
                    securityEngineId = rfc1902.OctetString(
                        hexValue=str(securityEngineId)
                    )
                securityName = server_config["usernames"][userName].get(
                    "securityName", None
                )
                authKeyType = int(
                    server_config["usernames"][userName].get("authKeyType", 0)
                )  # USM_KEY_TYPE_PASSPHRASE
                privKeyType = int(
                    server_config["usernames"][userName].get("privKeyType", 0)
                )  # USM_KEY_TYPE_PASSPHRASE
        except Exception as e:
            logger.error(
                f"Error happend while parsing parmas of UsmUserData for SNMP v3: {e}"
            )
        try:
            logger.debug(
                f"=============\nuserName - {userName}, authKey - {authKey}, privKey - {privKey}"
            )
            return UsmUserData(
                userName,
                authKey,
                privKey,
                authProtocol,
                privProtocol,
                securityEngineId,
                securityName,
                authKeyType,
                privKeyType,
            )
        except Exception as e:
            logger.error(f"Error happend while building UsmUserData for SNMP v3: {e}")
    else:
        try:
            # Essential params for SNMP v1/v2c
            # CommunityData(community_string, mpModel)
            communityName = community
            communityIndex = None
            contextEngineId = None
            contextName = None
            tag = None
            securityName = None
            if server_config["communities"].get(communityName, None):
                communityIndex = server_config["communities"][communityName].get(
                    "communityIndex", None
                )
                contextEngineId = server_config["communities"][communityName].get(
                    "contextEngineId", None
                )
                contextName = server_config["communities"][communityName].get(
                    "contextName", None
                )
                tag = server_config["communities"][communityName].get("tag", None)
                securityName = server_config["communities"][communityName].get(
                    "securityName", None
                )
            logger.debug(
                f"\ncommunityName - {communityName}, "
                f"communityIndex - {communityIndex}, "
                f"contextEngineId - {contextEngineId}, "
                f"contextName - {contextName}, "
                f"tag - {tag}, "
                f"securityName - {securityName}"
            )
        except Exception as e:
            logger.error(
                f"Error happend while parsing parmas of communityName for SNMP v1/v2c: {e}"
            )
        if version == "1":
            # for SNMP v1
            # CommunityData(community_string, mpModel=0)
            try:
                # return CommunityData(community, mpModel=0)
                mpModel = 0
                return CommunityData(
                    communityIndex,
                    communityName,
                    mpModel,
                    contextEngineId,
                    contextName,
                    tag,
                    securityName,
                )
            except Exception as e:
                logger.error(
                    f"Error happend while building CommunityData for SNMP v1: {e}"
                )
        else:
            # for SNMP v2c
            # CommunityData(community_string, mpModel=1)
            try:
                # return CommunityData(community, mpModel=1)
                mpModel = 1
                return CommunityData(
                    communityIndex,
                    communityName,
                    mpModel,
                    contextEngineId,
                    contextName,
                    tag,
                    securityName,
                )
            except Exception as e:
                logger.error(
                    f"Error happend while building CommunityData for SNMP v2c: {e}"
                )


def build_contextData(version, community, server_config):
    """
    create ContextData instance based on the SNMP's version
    for SNMP v1/v2c, use the default ContextData with contextName as empty string
    for SNMP v3, users can specify contextName, o.w. use empty string as contextName
    @params version: str, "1" | "2c" | "3"
    @params community:
        for v1/v2c: str, community string/community name, e.g. "public"
        for v3: str, userName
    @params server_config: dict of config.yaml
        for v3 to lookup authKey/privKey using userName
    @return ContextData class instance
        for v1/v2c: default ContextData(contextEngineId=None, contextName='')
        for v3: can specify contextName ContextData(contextEngineId=None, contextName=<contextName>)
    reference: https://pysnmp.readthedocs.io/en/latest/docs/api-reference.html
    """
    contextEngineId = None
    contextName = ""
    try:
        if version == "3" and server_config["usernames"].get(community, None):
            contextEngineId = server_config["usernames"][community].get(
                "contextEngineId", None
            )
            contextName = server_config["usernames"][community].get("contextName", "")
        logger.debug(
            f"======contextEngineId: {contextEngineId}, contextName: {contextName}============="
        )
    except Exception as e:
        logger.error(f"Error happend while parsing params for ContextData: {e}")
    try:
        return ContextData(contextEngineId, contextName)
    except Exception as e:
        logger.error(f"Error happend while building ContextData: {e}")


def is_oid(profile: str) -> bool:
    """
    This function checks if profile is an OID. OID is defined as a string of format:
        - ex. 1.3.6.1.2.1.2
        - ex. 1.3.6.2.1.*
    @param profile: variable from inventory file, can be a name of profile or an OID
    @return: if the profile is of OID structure
    """
    return bool(re.match(r"^\d(\.\d*)*(\.\*)?$", profile))
