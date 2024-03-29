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

from ..variables import enricher_additional_varbinds, enricher_existing_varbinds

logger = logging.getLogger(__name__)


def extract_current_index_from_metric(parsed_index):
    if parsed_index and "ifIndex" in parsed_index:
        return int(parsed_index["ifIndex"]) - 1
    return None


def extract_dimension_name_and_value(dimension_key, dimension_dict, index):
    dimension_values = dimension_dict[dimension_key]
    # We need to enrich only table data. Static values like IF-MIB::ifNumber.0 won't be enriched (it doesn't
    # make sense for those)
    if index is not None:
        if 0 <= index < len(dimension_values):
            return dimension_key, dimension_values[index]
    return None, None


class MibEnricher:
    def __init__(self, mib_static_data_collection):
        self._mib_static_data_collection = mib_static_data_collection

    def get_by_oid(self, oid_family):
        if oid_family not in self._mib_static_data_collection:
            return {}
        return self._mib_static_data_collection[oid_family]

    def get_by_oid_and_type(self, oid_family, type):
        oid_record = self.get_by_oid(oid_family)
        if not oid_record:
            oid_record = self.get_by_oid(oid_family.split(".")[1])
        return oid_record.get(type, {})

    def __enrich_if_mib_existing(self, metric_name, parsed_index):
        result = []
        if metric_name and metric_name.startswith(InterfaceMib.IF_MIB_METRIC_PREFIX):
            if self._mib_static_data_collection:
                if_mib_record = self.get_by_oid_and_type(
                    InterfaceMib.IF_MIB_METRIC_PREFIX, enricher_existing_varbinds
                )
                for dimension in if_mib_record:
                    index = extract_current_index_from_metric(parsed_index)
                    (
                        dimension_name,
                        dimension_value,
                    ) = extract_dimension_name_and_value(
                        dimension, if_mib_record, index
                    )
                    if dimension_name:
                        result.append({dimension_name: dimension_value})
        return result

    def __enrich_if_mib_additional(self, metric_name, parsed_index):
        for oid_family in self._mib_static_data_collection.keys():
            if oid_family in metric_name:
                try:
                    index = extract_current_index_from_metric(parsed_index)
                    if index is not None:
                        index_field = self.get_by_oid_and_type(
                            oid_family, enricher_additional_varbinds
                        )["indexNum"]
                        return [{index_field: index + 1}]
                except KeyError:
                    logger.debug("Enricher additionalVarBinds badly formatted")
                except TypeError:
                    logger.debug(f"Can't get the index from metric name: {metric_name}")
        return []

    def append_additional_dimensions(self, translated_var_bind, parsed_index):
        if translated_var_bind:
            metric_name = translated_var_bind[InterfaceMib.METRIC_NAME_KEY]
            additional_if_mib_dimensions = []
            fields_list = []
            if self._mib_static_data_collection:
                additional_if_mib_dimensions += self.__enrich_if_mib_existing(
                    metric_name, parsed_index
                )
                additional_if_mib_dimensions += self.__enrich_if_mib_additional(
                    metric_name, parsed_index
                )
            for more_data in additional_if_mib_dimensions:
                translated_var_bind.update(more_data)
                fields_list += list(more_data.keys())
            return fields_list
        else:
            logger.warning("None translated var binds, enrichment process will be skip")
