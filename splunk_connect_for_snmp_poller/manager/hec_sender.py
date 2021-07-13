#   ########################################################################
#   Copyright 2021 Splunk Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
#   ########################################################################
import time

import requests
import json

from celery.utils.log import get_logger

logger = get_logger(__name__)


def post_data_to_splunk_hec(
    host,
    logs_endpoint,
    metrics_endpoint,
    variables_binds,
    is_metric,
    index,
    one_time_flag=False,
):
    logger.debug(f"[-] logs : {logs_endpoint}, metrics : {metrics_endpoint}")

    if is_metric:
        logger.debug(f"+++++++++metric index: {index['metric_index']} +++++++++")
        post_metric_data(metrics_endpoint, host, variables_binds, index["metric_index"])
    else:
        logger.debug(f"*********event index: {index['event_index']} ********")
        post_event_data(
            logs_endpoint,
            host,
            variables_binds,
            index["event_index"],
            one_time_flag,
        )


# TODO Discuss the format of event data payload
def post_event_data(endpoint, host, variables_binds, index, one_time_flag=False):
    if "NoSuchInstance" in str(variables_binds):
        variables_binds = "error: " + str(variables_binds)

    data = {
        "time": time.time(),
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
        response = requests.post(url=endpoint, json=data, timeout=60)
        logger.debug(f"Response code is {response.status_code}")
        logger.debug(f"Response is {response.text}")
    except requests.ConnectionError as e:
        logger.error(f"Connection error when sending data to HEC index - {index}: {e}")


def post_metric_data(endpoint, host, variables_binds, index):

    json_val = json.loads(variables_binds)
    metric_name = json_val["metric_name"]
    metric_value = json_val["_value"]
    fields = {"metric_name:" + metric_name: metric_value}

    data = {
        "time": time.time(),
        "host": host,
        "index": index,
        "event": "metric",
        "fields": fields,
    }

    logger.debug(f"--------data------\n{data}")

    try:
        logger.debug(f"-----endpoint------\n{endpoint}")
        response = requests.post(url=endpoint, json=data, timeout=60)
        logger.debug(f"Response code is {response.status_code}")
        logger.debug(f"Response is {response.text}")
    except requests.ConnectionError as e:
        logger.error(f"Connection error when sending data to HEC index - {index}: {e}")
