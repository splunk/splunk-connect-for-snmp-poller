import logging
import requests
import re
import json

logger = logging.getLogger(__name__)

# TODO Remove debugging statement later

def post_data_to_splunk_hec(host, variables_binds, metric, index, hec_config):
    splunk_hec_token = hec_config.get_authentication_token()
    endpoints = hec_config.get_endpoints()
    logger.debug(f"[-] splunk_hec_token : {splunk_hec_token}")
    logger.debug(f"[-] endpoints : {endpoints}")
 
    # check if it is metric data
    for endpoint in endpoints:
        if metric:     
            logger.debug(f"+++++++++metric index: {index['metric_index']} +++++++++")
            post_metric_data(endpoint, splunk_hec_token, host, variables_binds, index["metric_index"])
        else:
            logger.debug(f"*********event index: {index['event_index']} ********")
            post_event_data(endpoint, splunk_hec_token, host, variables_binds, index["event_index"])
                   
# TODO Discuss the format of event data payload
def post_event_data(endpoint, token, host, variables_binds, index):
    headers = {
        "Authorization": f"Splunk {token}"
    }

    data = {
        "sourcetype": "sc4snmp:meta",
        "host": host,
        "index": index,
        "event": str(variables_binds),
    }

    if "error" in str(variables_binds):
        data["sourcetype"] = "sc4snmp:error"

    logger.debug(f"+++++++++headers+++++++++\n{headers}")
    logger.debug(f"+++++++++data+++++++++\n{data}")

    try:
        logger.debug(f"+++++++++endpoint+++++++++\n{endpoint}")
        response = requests.post(
            url=endpoint, json=data, headers=headers, verify=False
        )
        logger.debug(f"Response code is {response.status_code}")
        logger.debug(f"Response is {response.text}")
    except requests.ConnectionError as e:
        logger.error(f"Connection error when sending data to HEC index - {index}: {e}")


# TODO Discuss the format of metric data payload
def post_metric_data(endpoint, token, host, variables_binds, index):
    headers = {
        "Authorization": f"Splunk {token}"
    }

    data = {
        "host": host,
        "index": index,
        "fields": json.loads(variables_binds),
    }
    logger.debug(f"--------headers------\n{headers}")
    logger.debug(f"--------data------\n{data}")

    try:
        logger.debug(f"-----endpoint------\n{endpoint}")
        response = requests.post(
            url=endpoint, json=data, headers=headers, verify=False
        )
        logger.debug(f"Response code is {response.status_code}")
        logger.debug(f"Response is {response.text}")
    except requests.ConnectionError as e:
        logger.error(f"Connection error when sending data to HEC index - {index}: {e}")