from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

from splunk_connect_for_snmp_poller.manager.celery_client import app
from splunk_connect_for_snmp_poller.manager.mib_server_client import get_translation
from splunk_connect_for_snmp_poller.manager.hec_config import HecConfiguration
from splunk_connect_for_snmp_poller.manager.hec_sender import post_data_to_splunk_hec
from pysnmp.hlapi import *
import json
import os
from splunk_connect_for_snmp_poller.mongo import WalkedHostsRepository

from pysnmp.smi import builder, view, compiler, rfc1902
from pysmi import debug as pysmi_debug
pysmi_debug.setLogger(pysmi_debug.Debug('compiler'))


# TODO remove the debugging statement later 


@app.task
def snmp_get(host, version, community, profile, server_config, one_time_flag=False):
    mib_server_url = os.environ['MIBS_SERVER_URL']
    index =  {}
    index["event_index"]=  server_config["splunk"]["index"]["event"]
    index["metric_index"] = server_config["splunk"]["index"]["metric"]
    host, port = parse_port(host)
    hec_config = HecConfiguration()
    logger.info(f"Using the following MIBS server URL: {mib_server_url}")
    mongo_walked_hosts_coll = WalkedHostsRepository(server_config["mongo"])
    
    # create one SnmpEngie for get_handler, walk_handler, mib_string_handler
    snmp_engine = SnmpEngine()

    # results list contains all data ready to send out to Splunk HEC
    results = []

    # Handle mib-name
    if "." not in profile:
        # mib stuff     
        mib_profile = server_config["profiles"].get(profile, None)
        if mib_profile :
            varBinds = mib_profile.get('varBinds', None)
            logger.debug(f"======varBinds============\n{varBinds}")
            if varBinds:
                for varbind in varBinds:
                    logger.debug(f"======varbind============\n{varbind}")
                    # check if the varbind is mib string or oid
                    logger.debug(f"======varbind_list_flag===========\n{isinstance(varbind, list)}=")
                    if isinstance(varbind, list):
                        try:
                            mib_index = 0
                            if len(varbind) == 3:
                                mib_index = varbind[2]
                            mib_string_handler(snmp_engine, host, port, version, community, varbind[0], varbind[1], mib_index, mib_server_url, hec_config, server_config, results)
                        except Exception as e:
                            logger.error(f"Error happend while calling mib_string_handler(): {e}")
                    else:
                        try:
                            if varbind[-1] == "*":
                                walk_handler(snmp_engine, community, host, port, varbind, mib_server_url, hec_config, results)
                            else:
                                get_handler(snmp_engine, community, host, port, varbind, mib_server_url, hec_config, results) 
                        except Exception as e:
                            logger.error(f"Invalid format for oid. Error message: {e}")   
    #nextCmd - snmpwalk
    else:
        if profile[-1] == "*":
            logger.info(f'Executing SNMP WALK for {host} profile={profile}')
            walk_handler(snmp_engine, community, host, port, profile, mib_server_url, hec_config, results)
        # getCmd - snmpget
        else:       
            logger.info(f'Executing SNMP GET for {host} profile={profile}')
            get_handler(snmp_engine, community, host, port, profile, mib_server_url, hec_config, results) 
    
    logger.info(f"***results list with {len(results)} items***\n{results}")

    # Post mib event to splunk HEC
    for event, metric in results:
        post_data_to_splunk_hec(host, event, metric, index, hec_config, one_time_flag)

            
    return f'Executing SNMP GET for {host} version={version} profile={profile}'

def is_metric_data(hec_config, varBinds):
    """
    Check two conditions to see if the varBinds belongs to metric data. 
    1. if metric token exists
    2. if mib value is int/float 
    @param hec_config: HecConfiguration Object
    @param varBinds: varBinds Object
    @return: boolean
    """
    # check if the mib value is float
    for name, value in varBinds:
        try:
            float(value.prettyPrint())
            return True
        except ValueError:
            return False

def get_var_binds_string(mib_server_url, hec_config, varBinds):
    """
    Get the translated/formatted var_binds string depending on whether the varBinds is an event or metric
    Note: if it failed to get translation, return the the original varBinds
    @return result: formated string ready to be sent to Splunk HEC
    @return metric: boolean, metric data flag 
    """
    logger.info(f"I got these var binds: {varBinds}")
    # check if this is metric data
    metric = is_metric_data(hec_config, varBinds)
    # Get Original varbinds as backup in case the mib-server is unreachable
    # Set a tr-try block to retry if != 200
    try:
        for name, val in varBinds:             
            # Original oid
            # TODO Discuss: should we return the original oid 
            # if the mib server is unreachable
            # should we format it align with the format of the translated one
            # result = "{} = {}".format(name.prettyPrint(), val.prettyPrint())
            if metric:
                result = {
                    "metric_name": name.prettyPrint(),
                    "_value": val.prettyPrint(),
                }
                result = json.dumps(result)
            else: 
                result = '{oid}="{value}"'.format(oid=name.prettyPrint(), value=val.prettyPrint())

    except Exception as e:
        logger.info(f'Exception occured while logging varBinds name & value. Exception: {e}')

    # Overrid the varBinds string with translated varBinds string  
    try:
        result = get_translation(varBinds, mib_server_url, metric)
        logger.info(f"=========result=======\n{result}")
    except Exception as e:
        logger.info(f'Could not perform translation. Exception: {e}')
    logger.info(f"###############final result -- metric: {metric}#######################\n{result}")
    return result, metric


def mib_string_handler(snmp_engine, host, port, version, community, mib_file, mib_name, mib_index, mib_server_url, hec_config, server_config, results):
    logger.info(f"Executing get_by_mib_name() with {host} {port} {version} {community} {mib_file} {mib_name} {mib_index} {mib_server_url}")
    # TODO Should we create a spearate fun/module for mibViewController?
    mibBuilder = builder.MibBuilder()
    mibViewController = view.MibViewController(mibBuilder)
    config={'sources': [ os.environ['MIBS_FILES_URL'] ]}
    compiler.addMibCompiler(mibBuilder, **config)

    try:
        errorIndication, errorStatus, errorIndex, varBinds = next(
            getCmd(snmp_engine,
                CommunityData(community, mpModel=0),
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
            result, metric = get_var_binds_string(mib_server_url, hec_config, varBinds)
            results.append((result,metric))
    except Exception as e:
        print(f"Error happened while polling by mib name: {e}")

def get_handler(snmp_engine, community, host, port, profile, mib_server_url, hec_config, results):
    errorIndication, errorStatus, errorIndex, varBinds = next(
    getCmd(snmp_engine,
        CommunityData(community, mpModel=0),
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
        result, metric = get_var_binds_string(mib_server_url, hec_config, varBinds)
    results.append((result,metric))

def walk_handler(snmp_engine, community, host, port, profile, mib_server_url, hec_config, results):
    for (errorIndication,errorStatus,errorIndex,varBinds) in nextCmd(
        snmp_engine,
        CommunityData(community),
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
            result, metric = get_var_binds_string(mib_server_url, hec_config, varBinds)    
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

