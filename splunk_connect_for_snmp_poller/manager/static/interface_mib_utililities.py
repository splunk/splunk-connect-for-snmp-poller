#
# Copyright 2021 Splunk Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import logging

from splunk_connect_for_snmp_poller.manager.realtime.interface_mib import InterfaceMib
from splunk_connect_for_snmp_poller.utilities import multi_key_lookup

from ..variables import enricher_additional_varbinds, enricher_existing_varbinds

logger = logging.getLogger(__name__)


def __network_interface_enricher_attributes(config_as_dict, oid_family, varbinds_type):
    # TODO: we just assume here the whole structre of the poller's configuration
    # main file. If such section does not exist we simply do not anything.
    result = multi_key_lookup(
        config_as_dict, ("enricher", "oidFamily", oid_family, varbinds_type)
    )
    return result or []


def extract_network_interface_data_from_additional_config(config_as_dict):
    result = {}
    oid_families = config_as_dict["enricher"]["oidFamily"]
    for oid_family in oid_families.keys():
        additional_list = __network_interface_enricher_attributes(
            config_as_dict, oid_family, enricher_additional_varbinds
        )
        result[oid_family] = {}
        for el in additional_list:
            for key, values in el.items():
                result[oid_family][key] = values
    return result


def extract_network_interface_data_from_existing_config(config_as_dict):
    splunk_dimensions = __network_interface_enricher_attributes(
        config_as_dict, "IF-MIB", enricher_existing_varbinds
    )
    result = []
    if splunk_dimensions:
        for splunk_dimension in splunk_dimensions:
            for key in splunk_dimension.keys():
                result.append(
                    {
                        "oid_name": f"{InterfaceMib.IF_MIB_METRIC_PREFIX}{key}_",
                        "splunk_dimension_name": splunk_dimension[key],
                    }
                )
    logger.info(f"IF-MIB additional attributes for Splunk: {result}")
    return result


def extract_network_interface_data_from_walk(config_as_dict, if_mib_metric_walk_data):
    result = []
    network_data = InterfaceMib(if_mib_metric_walk_data)
    if network_data.has_consistent_data():
        enricher_fields = extract_network_interface_data_from_existing_config(
            config_as_dict
        )
        for data in enricher_fields:
            splunk_dimension = data["splunk_dimension_name"]
            current_result = network_data.extract_custom_field(data["oid_name"])
            if current_result:
                result.append({f"{splunk_dimension}": current_result})

    return result
