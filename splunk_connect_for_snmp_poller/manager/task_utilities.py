from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

from splunk_connect_for_snmp_poller.manager.mib_server_client import get_translation
from splunk_connect_for_snmp_poller.manager.hec_sender import post_data_to_splunk_hec
from pysnmp.hlapi import *
import json
import os

from pysnmp.smi import builder, view, compiler, rfc1902
from pysmi import debug as pysmi_debug
pysmi_debug.setLogger(pysmi_debug.Debug('compiler'))


# TODO remove the debugging statement later 

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
    @return metric: boolean, metric data flag 
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
            metric = is_metric_data(val.prettyPrint())
            if metric:
                result = {
                    "metric_name": name.prettyPrint(),
                    "_value": val.prettyPrint(),
                }
                result = json.dumps(result)
            else: 
                result = '{oid}="{value}"'.format(oid=name.prettyPrint(), value=val.prettyPrint())
    except Exception as e:
        logger.info(f'Exception occurred while logging varBinds name & value. Exception: {e}')

    # Overrid the varBinds string with translated varBinds string  
    try:
        logger.debug(f"==========result before translated -- metric={metric}============\n{result}")
        result = get_translation(varBinds, mib_server_url, metric)
        logger.info(f"=========result=======\n{result}")
        # TODO double check the result to handle the edge case, 
        # where the value of an metric data was translated from int to string
        if "metric_name" in result:
            result_dict = json.loads(result)
            _value = result_dict.get('_value', None)
            logger.debug(f"=========_value=======\n{_value}")
            if not is_metric_data(_value):
                metric=False
                result = get_translation(varBinds, mib_server_url, metric)
    except Exception as e:
        logger.info(f'Could not perform translation. Exception: {e}')
    logger.info(f"###############final result -- metric: {metric}#######################\n{result}")
    return result, metric


def mib_string_handler(snmp_engine, auth_data, context_data, host, port, mib_file, mib_name, mib_index, mib_server_url, server_config, results):
    """
    Perform the SNMP Get for mib-name/string, 
    e.g. ['SNMPv2-MIB', 'sysUpTime',0] (syntax -> [<mib_file_name>, <mib_name/string>, <min_index>])
    which querise the info correalted to this specific mib-name/string (e.g. sysUpTime)  
    """
    mibBuilder = builder.MibBuilder()
    mibViewController = view.MibViewController(mibBuilder)
    config={'sources': [ os.environ['MIBS_FILES_URL'] ]}
    compiler.addMibCompiler(mibBuilder, **config)

    try:
        errorIndication, errorStatus, errorIndex, varBinds = next(
            getCmd(snmp_engine,
                auth_data,
                UdpTransportTarget((host, port)),
                context_data,
                ObjectType(ObjectIdentity(mib_file, mib_name, mib_index)).resolveWithMib(mibViewController))               
        )

        if errorIndication:
            result = f"error: {errorIndication}"
            logger.info(result)
            results.append((result, False))
        elif errorStatus:
            result = 'error: %s at %s' % (errorStatus.prettyPrint(),
                                errorIndex and varBinds[int(errorIndex) - 1][0] or '?')
            logger.info(result)
            results.append((result, False))
        else:
            logger.info(f"varBinds: {varBinds}")
            for varBind in varBinds:
                logger.info(' = '.join([x.prettyPrint() for x in varBind]))
            result, metric = get_translated_string(mib_server_url, varBinds)
            results.append((result,metric))
    except Exception as e:
        logger.error(f"Error happened while polling by mib name: {e}")

def get_handler(snmp_engine, auth_data, context_data, host, port, profile, mib_server_url, results):
    """
    Perform the SNMP Get for an oid, 
    e.g. 1.3.6.1.2.1.1.9.1.2.1, 
    which queries the info correalted to this specific oid 
    """
    errorIndication, errorStatus, errorIndex, varBinds = next(
    getCmd(snmp_engine,
        auth_data,
        UdpTransportTarget((host, port)),
        context_data,
        ObjectType(ObjectIdentity(profile)))
    )
    if errorIndication:
        result = f"error: {errorIndication}"
        metric = False
        logger.error(result)
    elif errorStatus:
        result = 'error: %s at %s' % (errorStatus.prettyPrint(),
                            errorIndex and varBinds[int(errorIndex) - 1][0] or '?')
        metric = False
        logger.error(result)
    else:
        result, metric = get_translated_string(mib_server_url, varBinds)
        
    results.append((result,metric))

def walk_handler(snmp_engine, auth_data, context_data, host, port, profile, mib_server_url, results):
    """
    Perform the SNMP Walk for oid end with *, 
    e.g. 1.3.6.1.2.1.1.9.*, 
    which queries the infos correalted to all the oids that underneath the prefix before the *, e.g. 1.3.6.1.2.1.1.9
    """
    for (errorIndication,errorStatus,errorIndex,varBinds) in nextCmd(
        snmp_engine,
        auth_data,
        UdpTransportTarget((host, port)),
        context_data,
        ObjectType(ObjectIdentity(profile[:-2])),lexicographicMode=False):

        if errorIndication:
            result = f"error: {errorIndication}"
            logger.info(result)
            results.append((result, False))
            break
        elif errorStatus:
            result = 'error: %s at %s' % (errorStatus.prettyPrint(),
                errorIndex and varBinds[int(errorIndex) - 1][0] or '?')
            logger.info(result)
            results.append((result, False))
            break
        else:
            result, metric = get_translated_string(mib_server_url, varBinds)    
            results.append((result, metric))

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

                authProtocol = server_config["usernames"][userName].get("authProtocol", None)
                privProtocol = server_config["usernames"][userName].get("privProtocol", None)
                securityEngineId = server_config["usernames"][userName].get("securityEngineId", None)
                securityName = server_config["usernames"][userName].get("securityName", None)
                authKeyType = server_config["usernames"][userName].get("authKeyType", 0) # USM_KEY_TYPE_PASSPHRASE
                privKeyType = server_config["usernames"][userName].get("privKeyType", 0) # USM_KEY_TYPE_PASSPHRASE
        except Exception as e:
            logger.error(f"Error happend while parsing parmas of UsmUserData for SNMP v3: {e}") 
        try:
            logger.debug(f"=============\nuserName - {userName}, authKey - {authKey}, privKey - {privKey}")
            return UsmUserData(userName, authKey, privKey, authProtocol, privProtocol, securityEngineId, securityName, authKeyType, privKeyType)
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
                communityIndex = server_config["communities"][communityName].get("communityIndex", None)
                contextEngineId = server_config["communities"][communityName].get("contextEngineId", None)
                contextName = server_config["communities"][communityName].get("contextName", None)
                tag = server_config["communities"][communityName].get("tag", None)
                securityName = server_config["communities"][communityName].get("securityName", None)
        except Exception as e:
            logger.error(f"Error happend while parsing parmas of communityName for SNMP v1/v2c: {e}")    
        if version == "1":
            # for SNMP v1
            # CommunityData(community_string, mpModel=0)
            try: 
                # return CommunityData(community, mpModel=0)
                mpModel = 0
                return CommunityData(communityIndex, communityName, mpModel,contextEngineId, contextName, tag, securityName)
            except Exception as e:
                logger.error(f"Error happend while building CommunityData for SNMP v1: {e}")       
        else:
            # for SNMP v2c
            # CommunityData(community_string, mpModel=1)
            try: 
                # return CommunityData(community, mpModel=1)
                mpModel = 1
                return CommunityData(communityIndex, communityName, mpModel,contextEngineId, contextName, tag, securityName)
            except Exception as e:
                logger.error(f"Error happend while building CommunityData for SNMP v2c: {e}") 

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
            contextEngineId = server_config["usernames"][community].get("contextEngineId", None)
            contextName = server_config["usernames"][community].get("contextName", "")
        logger.debug(f"======contextEngineId: {contextEngineId}, contextName: {contextName}=============")
    except Exception as e:
        logger.error(f"Error happend while parsing params for ContextData: {e}")
    try:
        return ContextData(contextEngineId, contextName)
    except Exception as e:
        logger.error(f"Error happend while building ContextData: {e}")
    
        



