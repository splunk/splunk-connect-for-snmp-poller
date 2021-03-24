from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

from splunk_connect_for_snmp_poller.manager.celery_client import app
from splunk_connect_for_snmp_poller.manager.hec_config import HecConfiguration
from splunk_connect_for_snmp_poller.manager.hec_sender import post_data_to_splunk_hec
from splunk_connect_for_snmp_poller.manager.task_utilities import get_handler, walk_handler, mib_string_handler, parse_port, build_authData
from pysnmp.hlapi import *
import os
from splunk_connect_for_snmp_poller.mongo import WalkedHostsRepository


# TODO remove the debugging statement later 


@app.task
def snmp_polling(host, version, community, profile, server_config, one_time_flag=False):
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

    # create auth_data depending on SNMP's version
    # TODO discuss how to handle when auth_data == None 
    # Added try catch below
    auth_data = build_authData(version, community, server_config)
    logger.debug(f"==========auth_data=========\n{auth_data}")


    # results list contains all data ready to send out to Splunk HEC
    results = []
    
    try:
        # Perform SNNP Polling for string profile in inventory.csv
        if "." not in profile:
            logger.info(f'Executing SNMP Polling for Varbinds in config.yaml for {host} profile={profile}')   
            mib_profile = server_config["profiles"].get(profile, None)
            if mib_profile :
                varBinds = mib_profile.get('varBinds', None)
                if varBinds:
                    for varbind in varBinds:
                        # check if the varbind is mib string or oid
                        if isinstance(varbind, list):
                            # Perform SNMP polling for mib string
                            try:
                                mib_index = 0
                                if len(varbind) == 3:
                                    mib_index = varbind[2]
                                mib_string_handler(snmp_engine, auth_data, host, port, varbind[0], varbind[1], mib_index, mib_server_url, hec_config, server_config, results)
                            except Exception as e:
                                logger.error(f"Error happend while calling mib_string_handler(): {e}")
                        else:
                            # Perform SNMP polling for oid
                            try:
                                if varbind[-1] == "*":
                                    walk_handler(snmp_engine, auth_data, host, port, varbind, mib_server_url, hec_config, results)
                                else:
                                    get_handler(snmp_engine, auth_data, host, port, varbind, mib_server_url, hec_config, results) 
                            except Exception as e:
                                logger.error(f"Invalid format for oid. Error message: {e}")   
        # Perform SNNP Polling for oid profile in inventory.csv
        else:
            # Perform SNNP WALK for oid end with *
            if profile[-1] == "*":
                logger.info(f'Executing SNMP WALK for {host} profile={profile}')
                walk_handler(snmp_engine, auth_data, host, port, profile, mib_server_url, hec_config, results)
            # Perform SNNP GET for an oid 
            else:       
                logger.info(f'Executing SNMP GET for {host} profile={profile}')
                get_handler(snmp_engine, auth_data, host, port, profile, mib_server_url, hec_config, results) 
        
        logger.info(f"***results list with {len(results)} items***\n{results}")

        # Post mib event to splunk HEC
        for event, metric in results:
            post_data_to_splunk_hec(host, event, metric, index, hec_config, one_time_flag)

                
        return f'Executing SNMP Polling for {host} version={version} profile={profile}'
    except Exception as e:
        logger.error(f"Error happend while executing SNMP polling for {host}, version={version}, profile={profile}: {e}")