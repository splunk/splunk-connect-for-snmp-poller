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
from collections import namedtuple

from celery.utils.log import get_task_logger
from pysmi import debug as pysmi_debug
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
from splunk_connect_for_snmp_poller.manager.hec_sender import (
    post_data_to_splunk_hec,
)
from splunk_connect_for_snmp_poller.manager.mib_server_client import (
    get_translation,
)

pysmi_debug.setLogger(pysmi_debug.Debug("compiler"))
logger = get_task_logger(__name__)


class VarbindCollection(namedtuple("VarbindCollection", "get, bulk")):
    def __add__(self, other):
        return VarbindCollection(bulk=self.bulk + other.bulk, get=self.get + other.get)


# TODO remove the debugging statement later
# TODO analyze the code here:
# https://github.com/etingof/pysnmp/blob/becd15c79c9a6b5696928ecd50bf5cca8b1770a1/examples/hlapi/v3arch/asyncore/manager/cmdgen/pull-mibs-from-multiple-agents-at-once-over-ipv4-and-ipv6.py#L57
# to compare the performace between the runDispatcher() and the current getCmd()/nextCmd() .


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


def get_translated_string(mib_server_url, varBinds):
    """
    Get the translated/formatted var_binds string depending on whether the varBinds is an event or metric
    Note: if it failed to get translation, return the the original varBinds
    @return result: formated string ready to be sent to Splunk HEC
    @return is_metric: boolean, metric data flag
    """
    logger.info(f"I got these var binds: {varBinds}")
    # Get Original varbinds as backup in case the mib-server is unreachable
    try:
        for name, val in varBinds:
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
                result = '{oid}="{value}"'.format(
                    oid=name.prettyPrint(), value=val.prettyPrint()
                )
    except Exception as e:
        logger.info(
            f"Exception occurred while logging varBinds name & value. Exception: {e}"
        )

    # Override the varBinds string with translated varBinds string
    try:
        logger.debug(
            f"==========result before translated -- is_metric={is_metric}============\n{result}"
        )
        result = get_translation(varBinds, mib_server_url, is_metric)
        logger.info(f"=========result=======\n{result}")
        # TODO double check the result to handle the edge case,
        # where the value of an metric data was translated from int to string
        if "metric_name" in result:
            result_dict = json.loads(result)
            _value = result_dict.get("_value", None)
            logger.debug(f"=========_value=======\n{_value}")
            if not is_metric_data(_value):
                is_metric = False
                result = get_translation(varBinds, mib_server_url, is_metric)
    except Exception as e:
        logger.info(f"Could not perform translation. Exception: {e}")
    logger.info(
        f"###############final result -- metric: {is_metric}#######################\n{result}"
    )
    return result, is_metric


def mib_string_handler(mib_list: list) -> VarbindCollection:
    """
    Perform the SNMP Get for mib-name/string, where mib string is a list
    1) case 1: with mib index - consider it as a single oid -> snmpget
    e.g. ['SNMPv2-MIB', 'sysUpTime',0] (syntax -> [<mib_file_name>, <mib_name/string>, <min_index>])

    2) case 2: without mib index - consider it as a oid with * -> snmpbulk
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
                    (
                        f"Invalid mib string - {mib_string}."
                        f"\nPlease provide a valid mib string in the correct format. "
                        f"Learn more about the format at https://bit.ly/3qtqzQc"
                    )
                )
        except Exception as e:
            logger.error(
                f"Error happened while polling for mib string: {mib_string}: {e}"
            )
    return VarbindCollection(get=get_list, bulk=bulk_list)


def snmp_get_handler(
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
    if not _any_failure_happened(
            errorIndication, errorStatus, errorIndex, varBinds
        ):
        for varbind in varBinds:
            result, is_metric = get_translated_string(mib_server_url, [varbind])
            post_data_to_splunk_hec(
                host,
                otel_logs_url,
                otel_metrics_url,
                result,
                is_metric,
                index,
                one_time_flag,
            )


def _any_failure_happened(
    errorIndication, errorStatus: int, errorIndex: int, varBinds: list
) -> bool:
    """
    This function checks if any failure happened during GET or BULK operation.
    @param errorIndication:
    @param errorStatus:
    @param errorIndex: index of varbind where error appeared
    @param varBinds: list of varbinds
    @return: if any failure happened
    """
    if errorIndication:
        result = f"error: {errorIndication}"
        logger.error(result)
    elif errorStatus:
        result = "error: %s at %s" % (
            errorStatus.prettyPrint(),
            errorIndex and varBinds[int(errorIndex) - 1][0] or "?",
        )
        logger.error(result)
    else:
        return False
    return True


def snmp_bulk_handler(
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
    for (errorIndication, errorStatus, errorIndex, varBinds) in g:
        if not _any_failure_happened(
            errorIndication, errorStatus, errorIndex, varBinds
        ):
            # Bulk operation returns array of varbinds
            for varbind in varBinds:
                logger.debug(f"Bulk returned this varbind: {varbind}")
                result, is_metric = get_translated_string(mib_server_url, [varbind])
                logger.info(result)
                post_data_to_splunk_hec(
                    host,
                    otel_logs_url,
                    otel_metrics_url,
                    result,
                    is_metric,
                    index,
                    one_time_flag,
                )


def walk_handler(
    profile,
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
    """
    Perform the SNMP Walk for oid end with *,
    e.g. 1.3.6.1.2.1.1.9.*,
    which queries the infos correlated to all the oids that underneath the prefix before the *, e.g. 1.3.6.1.2.1.1.9
    """

    for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
        snmp_engine,
        auth_data,
        UdpTransportTarget((host, port)),
        context_data,
        ObjectType(ObjectIdentity(profile[:-2])),
        lexicographicMode=False,
    ):
        is_metric = False
        if errorIndication:
            result = f"error: {errorIndication}"
            logger.info(result)
            post_data_to_splunk_hec(
                host,
                otel_logs_url,
                otel_metrics_url,
                result,
                is_metric,
                index,
                one_time_flag,
            )
            break
        elif errorStatus:
            result = "error: %s at %s" % (
                errorStatus.prettyPrint(),
                errorIndex and varBinds[int(errorIndex) - 1][0] or "?",
            )
            logger.info(result)
            post_data_to_splunk_hec(
                host,
                otel_logs_url,
                otel_metrics_url,
                result,
                is_metric,
                index,
                one_time_flag,
            )
            break
        else:
            result, is_metric = get_translated_string(mib_server_url, varBinds)
            post_data_to_splunk_hec(
                host,
                otel_logs_url,
                otel_metrics_url,
                result,
                is_metric,
                index,
                one_time_flag,
            )


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
