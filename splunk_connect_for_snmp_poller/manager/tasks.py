import logging
logger = logging.getLogger(__name__)

from splunk_connect_for_snmp_poller.manager.celery_client import app
from splunk_connect_for_snmp_poller.manager.mib_server_client import get_translation
from splunk_connect_for_snmp_poller.manager.hec_config import HecConfiguration
from splunk_connect_for_snmp_poller.manager.hec_sender import post_data_to_splunk_hec
from pysnmp.hlapi import *
import json


@app.task
def snmp_get(host, port, version, community, profile, mib_server_url, index):
    hec_config = HecConfiguration()
    results = []
    #nextCmd - snmpwalk
    if profile[-1] == "*":
        logger.debug(f'Executing SNMP WALK for {host} profile={profile}')
        for (errorIndication,errorStatus,errorIndex,varBinds) in nextCmd(
            SnmpEngine(),
            CommunityData(community),
            # TODO do we have port in inventory.csv
            UdpTransportTarget((host, port)),
            ContextData(),
            ObjectType(ObjectIdentity(profile[:-2])),lexicographicMode=False):
        
            if errorIndication:
                result = errorIndication
                logger.debug(result)
                results.append((result, False))
                break
            elif errorStatus:
                result = '%s at %s' % (errorStatus.prettyPrint(),
                    errorIndex and varBinds[int(errorIndex) - 1][0] or '?')
                logger.debug(result)
                results.append((result, False))
                break
            else:
                result, metric = get_var_binds_string(mib_server_url, hec_config, varBinds)    
                results.append((result, metric))
    # getCmd - snmpget
    else:       
        logger.debug(f'Executing SNMP GET for {host} profile={profile}')       
        # check if it's in mongo
        errorIndication, errorStatus, errorIndex, varBinds = next(
        getCmd(SnmpEngine(),
            CommunityData(community, mpModel=0),
            # TODO do we have port in inventory.csv
            UdpTransportTarget((host, port)),
            ContextData(),
            ObjectType(ObjectIdentity(profile)))
        )
        if errorIndication:
            result = errorIndication
            metric = False
            logger.error(result)
        elif errorStatus:
            result = '%s at %s' % (errorStatus.prettyPrint(),
                                errorIndex and varBinds[int(errorIndex) - 1][0] or '?')
            metric = False
            logger.error(result)
        else:
            result, metric = get_var_binds_string(mib_server_url, hec_config, varBinds)
        results.append((result,metric))
       
    
    logger.debug(f"***results list with {len(results)} items***\n{results}")

    # Post mib event to splunk HEC
    for event, metric in results:
        post_data_to_splunk_hec(host, event, metric, index, hec_config)

            
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
    splunk_hec_metric_token = hec_config.get_authentication_metric_token()
    # check if the metric token exist
    if splunk_hec_metric_token:
        # check if the mib value is float
        for name, value in varBinds:
            try:
                float(value.prettyPrint())
                return True
            except ValueError:
                return False
    else:
        return False

def get_var_binds_string(mib_server_url, hec_config, varBinds):
    """
    Get the translated/formatted var_binds string depending on whether the varBinds is an event or metric
    Note: if it failed to get translation, return the the original varBinds
    @return result: formated string ready to be sent to Splunk HEC
    @return metric: boolean, metric data flag 
    """
    # check if this is metric data
    metric = is_metric_data(hec_config, varBinds)
    # Get Original varbinds as backup in case the mib-server is unreachable
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
                result = "{} = {}".format(name.prettyPrint(), val.prettyPrint())

    except Exception as e:
        logger.debug(f'Exception occured while logging varBinds name & value. Exception: {e}') 

    # Overrid the varBinds string with translated varBinds string  
    try:
        result = get_translation(varBinds, mib_server_url, metric)
        logger.debug(f"=========result=======\n{result}")
    except Exception as e:
        logger.debug(f'Could not perform translation. Exception: {e}')
    logger.debug(f"###############final result -- metric: {metric}#######################\n{result}")
    return result, metric

