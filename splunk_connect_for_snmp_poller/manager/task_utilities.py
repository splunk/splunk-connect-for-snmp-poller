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


def mib_string_handler(snmp_engine, auth_data, host, port, mib_file, mib_name, mib_index, mib_server_url, server_config, results):
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
                ContextData(),
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

def get_handler(snmp_engine, auth_data, host, port, profile, mib_server_url, results):
    """
    Perform the SNMP Get for an oid, 
    e.g. 1.3.6.1.2.1.1.9.1.2.1, 
    which queries the info correalted to this specific oid 
    """
    errorIndication, errorStatus, errorIndex, varBinds = next(
    getCmd(snmp_engine,
        auth_data,
        UdpTransportTarget((host, port)),
        ContextData(),
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

def walk_handler(snmp_engine, auth_data, host, port, profile, mib_server_url, results):
    """
    Perform the SNMP Walk for oid end with *, 
    e.g. 1.3.6.1.2.1.1.9.*, 
    which queries the infos correalted to all the oids that underneath the prefix before the *, e.g. 1.3.6.1.2.1.1.9
    """
    for (errorIndication,errorStatus,errorIndex,varBinds) in nextCmd(
        snmp_engine,
        auth_data,
        UdpTransportTarget((host, port)),
        ContextData(),
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
        for v1/v2c: str, community string, e.g. "public"
        for v3: str, userName
    @params server_config: dict of config.yaml
        for v3 to lookup authKey/privKey using userName
    @return authData class instance 
        for v1/v2c: CommunityData class instance 
        for v3: UsmUserData class instance 
    """
    if version == "3":
        try:
            # for SNMP v3
            # UsmUserData(userName, authKey=None, privKey=None)
            userName = community
            authKey = server_config["usernames"][userName].get("authKey", None)
            privKey = server_config["usernames"][userName].get("privKey", None)
            logger.debug(f"=============\nuserName - {userName}, authKey - {authKey}, privKey - {privKey}")
            return UsmUserData(userName, authKey, privKey)
        except Exception as e:
            logger.error(f"Error happend while building UsmUserData for SNMP v3: {e}")       
    elif version == "1":
        # for SNMP v1
        # CommunityData(community_string, mpModel=0)
        try: 
            return CommunityData(community, mpModel=0)
        except Exception as e:
            logger.error(f"Error happend while building CommunityData for SNMP v1: {e}")       
    else:
        # for SNMP v2c
        # CommunityData(community_string, mpModel=1)
        try: 
            return CommunityData(community, mpModel=1)
        except Exception as e:
            logger.error(f"Error happend while building CommunityData for SNMP v2c: {e}") 
