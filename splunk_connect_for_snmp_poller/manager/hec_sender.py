import logging
import requests
import json

logger = logging.getLogger(__name__)

# TODO Remove debugging statement later

def post_data_to_splunk_hec(host, logs_endpoint, metrics_endpoint, variables_binds, metric, index, one_time_flag=False):
    logger.debug(f"[-] logs : {logs_endpoint}, metrics : {metrics_endpoint}")
    # check if it is metric data
    if metric:
        logger.debug(f"+++++++++metric index: {index['metric_index']} +++++++++")
        post_metric_data(metrics_endpoint, host, variables_binds, index["metric_index"])
    else:
        logger.debug(f"*********event index: {index['event_index']} ********")
        post_event_data(logs_endpoint, host, variables_binds, index["event_index"], one_time_flag)


# TODO Discuss the format of event data payload
def post_event_data(endpoint, host, variables_binds, index, one_time_flag=False):
    if "NoSuchInstance" in str(variables_binds):
        variables_binds = "error: " + str(variables_binds)

    data = {
        "sourcetype": "sc4snmp:meta",
        "host": host,
        "index": index,
        "event": str(variables_binds),
    }

    if one_time_flag:
        data["sourcetype"] = "sc4snmp:walk"

    if "error" in str(variables_binds):
        data["sourcetype"] = "sc4snmp:error"

    logger.debug(f"+++++++++data+++++++++\n{data}")

    try:
        logger.debug(f"+++++++++endpoint+++++++++\n{endpoint}")
        response = requests.post(
            url=endpoint, json=data
        )
        logger.debug(f"Response code is {response.status_code}")
        logger.debug(f"Response is {response.text}")
    except requests.ConnectionError as e:
        logger.error(f"Connection error when sending data to HEC index - {index}: {e}")


# TODO Discuss the format of metric data payload
def post_metric_data(endpoint, host, variables_binds, index):

    data = {
        "host": host,
        "index": index,
        "fields": json.loads(variables_binds),
    }
    logger.debug(f"--------data------\n{data}")

    try:
        logger.debug(f"-----endpoint------\n{endpoint}")
        response = requests.post(
            url=endpoint, json=data
        )
        logger.debug(f"Response code is {response.status_code}")
        logger.debug(f"Response is {response.text}")
    except requests.ConnectionError as e:
        logger.error(f"Connection error when sending data to HEC index - {index}: {e}")