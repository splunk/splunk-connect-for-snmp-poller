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
import json
import time

import requests
from celery.utils.log import get_logger

from splunk_connect_for_snmp_poller.manager.static.mib_enricher import MibEnricher

logger = get_logger(__name__)


def post_data_to_splunk_hec(
    host,
    logs_endpoint,
    metrics_endpoint,
    variables_binds,
    is_metric,
    index,
    one_time_flag=False,
    mib_enricher=None,
):
    logger.debug(f"[-] logs : {logs_endpoint}, metrics : {metrics_endpoint}")

    if is_metric:
        logger.debug(f"+++++++++metric index: {index['metric_index']} +++++++++")
        post_metric_data(
            metrics_endpoint, host, variables_binds, index["metric_index"], mib_enricher
        )
    else:
        logger.debug(f"*********event index: {index['event_index']} ********")
        post_event_data(
            logs_endpoint,
            host,
            variables_binds,
            index["event_index"],
            one_time_flag,
            mib_enricher,
        )


# TODO Discuss the format of event data payload
def post_event_data(
    endpoint, host, variables_binds, index, one_time_flag=False, mib_enricher=None
):
    if "NoSuchInstance" in str(variables_binds):
        variables_binds = "error: " + str(variables_binds)

    elif mib_enricher:
        variables_binds = _enrich_event_data(mib_enricher, json.loads(variables_binds))
    elif "non_metric" in variables_binds:
        variables_binds = json.loads(variables_binds)["non_metric"]

    # if "IF-MIB" in variables_binds:
    #     index_num = return_event_index_number(variables_binds)
    #     variables_binds += f"index_num={index_num} "

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


def _enrich_event_data(mib_enricher: MibEnricher, variables_binds: dict) -> str:
    """
    This function serves for processing event data the way we add additional dimensions configured in enricher config.
    @param mib_enricher: MibEnricher object containing additional dimensions
    @param variables_binds: dictionary containing "metric_name", "metric" - metric version of varbinds and
    "non_metric" - nonmetric version of varbinds, for ex:

    {'metric': '{"metric_name": "sc4snmp.IF-MIB.ifPhysAddress_1", "_value": "", "metric_type": "OctetString"}',
    'metric_name': 'sc4snmp.IF-MIB.ifPhysAddress_1',
    'non_metric': 'oid-type1="ObjectIdentity" value1-type="OctetString" 1.3.6.1.2.1.2.2.1.6.1=""
    value1="" IF-MIB::ifPhysAddress.1="" '}

    We need both formats because append_additional_dimensions function was designed to work on metric data only and non
    metric format is
    difficult to process because of the nature of string type.

    @return: non metric varbind with values from additional dimension added. For ex. for additional dimensions:
    [interface_index, interface_desc]:
    'oid-type1="ObjectIdentity" value1-type="OctetString" 1.3.6.1.2.1.2.2.1.6.1="" value1="" IF-MIB::ifPhysAddress.1=""
    interface_index="1" interface_desc="lo" '
    """
    metric_result = json.loads(variables_binds["metric"])
    non_metric_result = variables_binds["non_metric"]
    additional_dimensions = mib_enricher.append_additional_dimensions(metric_result)
    for field_name in additional_dimensions:
        if field_name in metric_result:
            non_metric_result += f'{field_name}="{metric_result[field_name]}" '
    return non_metric_result


def post_metric_data(endpoint, host, variables_binds, index, mib_enricher=None):
    json_val = json.loads(variables_binds)
    metric_name = json_val["metric_name"]
    metric_value = json_val["_value"]
    fields = {"metric_name:" + metric_name: metric_value}
    if mib_enricher:
        _enrich_metric_data(mib_enricher, json_val, fields)

    # if "IF-MIB" in variables_binds:
    #     metric_index = return_metrics_index_number(json_val)
    #     fields["num_index"] = metric_index

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


def _enrich_metric_data(
    mib_enricher: MibEnricher, variables_binds: dict, fields: dict
) -> None:
    additional_if_mib_dimensions = mib_enricher.append_additional_dimensions(
        variables_binds
    )
    for field_name in additional_if_mib_dimensions:
        if field_name in variables_binds:
            fields[field_name] = variables_binds[field_name]
