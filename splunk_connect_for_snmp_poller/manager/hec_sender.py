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

from splunk_connect_for_snmp_poller.manager.data.event_builder import (
    EventBuilder,
    EventField,
    EventType,
)
from splunk_connect_for_snmp_poller.manager.data.inventory_record import InventoryRecord
from splunk_connect_for_snmp_poller.manager.static.mib_enricher import MibEnricher
from splunk_connect_for_snmp_poller.manager.variables import enricher_name, enricher_oid_family

logger = get_logger(__name__)


class HecSender:
    def __init__(self, metrics_endpoint, logs_endpoint):
        logger.debug(f"[-] logs : {logs_endpoint}, metrics : {metrics_endpoint}")
        self.metrics_endpoint = metrics_endpoint
        self.logs_endpoint = logs_endpoint

    def send_hec_request(self, is_metric: bool, data):
        if is_metric:
            return self.send_metric_request(data)
        else:
            return self.send_event_request(data)

    def send_event_request(self, data):
        return HecSender.send_request(self.logs_endpoint, data)

    def send_metric_request(self, data):
        return HecSender.send_request(self.metrics_endpoint, data)

    @staticmethod
    def send_request(endpoint, data):
        try:
            logger.debug("+++++++++endpoint+++++++++\n%s", endpoint)
            response = requests.post(url=endpoint, json=data, timeout=60)
            logger.debug("Response code is %s", response.status_code)
            logger.debug("Response is %s", response.text)
            return response
        except requests.ConnectionError as e:
            logger.error(
                f"Connection error when sending data to HEC index - {data['index']}: {e}"
            )


def post_data_to_splunk_hec(
    hec_sender: HecSender,
    host,
    variables_binds,
    is_metric,
    index,
    ir: InventoryRecord,
    additional_metric_fields,
    server_config,
    one_time_flag=False,
    mib_enricher=None,
    is_error=False,
):
    if is_error:
        logger.debug("sending error to index - %s", index["event_index"])
        data = build_error_data(host, variables_binds, index["event_index"])
    elif is_metric:
        logger.debug("metric index: %s", index["metric_index"])
        data = build_metric_data(
            host,
            variables_binds,
            index["metric_index"],
            ir,
            additional_metric_fields,
            server_config,
            mib_enricher,
        )
    else:
        logger.debug("event index - %s", index["event_index"])
        data = build_event_data(
            host,
            variables_binds,
            index,
            one_time_flag=one_time_flag,
            mib_enricher=mib_enricher,
        )
    hec_sender.send_hec_request(is_metric, data)


# TODO Discuss the format of event data payload
def build_event_data(
    host, variables_binds, indexes, one_time_flag=False, mib_enricher=None
):
    variables_binds = prepare_variable_binds(mib_enricher, variables_binds)

    builder = init_builder_with_common_data(time.time(), host, indexes["meta_index"])
    builder.add(EventField.SOURCETYPE, EventType.EVENT.value)
    builder.add(EventField.EVENT, str(variables_binds))
    builder.is_one_time_walk(one_time_flag)

    if "error" in str(variables_binds):
        builder.add(EventField.INDEX, indexes["event_index"])
        builder.add(EventField.SOURCETYPE, EventType.ERROR.value)

    return builder.build()


def init_builder_with_common_data(current_time, host, index) -> EventBuilder:
    builder = EventBuilder()
    builder.add(EventField.TIME, current_time)
    builder.add(EventField.HOST, host)
    builder.add(EventField.INDEX, index)
    return builder


def prepare_variable_binds(mib_enricher, variables_binds):
    if "NoSuchInstance" in str(variables_binds):
        variables_binds = "error: " + str(variables_binds)
    elif mib_enricher:
        variables_binds = _enrich_event_data(mib_enricher, json.loads(variables_binds))
    elif "non_metric" in variables_binds:
        variables_binds = json.loads(variables_binds)["non_metric"]
    return variables_binds


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
    logger.debug(additional_dimensions)
    for field_name in additional_dimensions:
        if field_name in metric_result:
            if metric_result[field_name]:
                non_metric_result += f'{field_name}="{metric_result[field_name]}" '
    return non_metric_result


def build_metric_data(
    host,
    variables_binds,
    index,
    ir: InventoryRecord,
    additional_metric_fields,
    server_config,
    mib_enricher=None,
):
    json_val = json.loads(variables_binds)
    metric_name = json_val["metric_name"]
    metric_value = json_val["_value"]
    fields = {
        "metric_name:" + metric_name: metric_value,
        EventField.FREQUENCY.value: ir.frequency_str,
    }
    if mib_enricher:
        _enrich_metric_data(mib_enricher, json_val, fields)

    if additional_metric_fields:
        fields = ir.extend_dict_with_provided_data(fields, additional_metric_fields)

    builder = init_builder_with_common_data(time.time(), host, index)
    builder.add(EventField.EVENT, EventType.METRIC.value)

    strip_trailing_index_number(fields, metric_name, metric_value, server_config)

    builder.add_fields(fields)
    return builder.build()


def strip_trailing_index_number(fields, metric_name, metric_value, server_config):
    oid_families = server_config[enricher_name][enricher_oid_family].keys()
    if any(metric_name.startswith("sc4snmp." + x) for x in oid_families):
        stripped = metric_name[:metric_name.rindex('_')]
        del fields["metric_name:" + metric_name]
        fields["metric_name:" + stripped] = metric_value


def build_error_data(
    host,
    variables_binds,
    index,
):
    builder = init_builder_with_common_data(time.time(), host, index)
    builder.add(EventField.EVENT, str(variables_binds))
    builder.add(EventField.SOURCETYPE, EventType.ERROR.value)
    return builder.build()


def _enrich_metric_data(
    mib_enricher: MibEnricher, variables_binds: dict, fields: dict
) -> None:
    additional_if_mib_dimensions = mib_enricher.append_additional_dimensions(
        variables_binds
    )
    for field_name in additional_if_mib_dimensions:
        if field_name in variables_binds:
            if variables_binds[field_name]:
                fields[field_name] = variables_binds[field_name]
