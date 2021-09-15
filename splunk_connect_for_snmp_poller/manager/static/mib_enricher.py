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

logger = logging.getLogger(__name__)


def extract_current_index_from_metric(current_translated_oid):
    try:
        if current_translated_oid:
            return (
                int(
                    current_translated_oid[
                        current_translated_oid.rindex("_") + 1 :  # noqa: E203
                    ]
                )
                - 1
            )
    except ValueError:
        logger.warning(
            f"Could not find any index for {current_translated_oid}. This will not be enriched"
        )

    return None


def extract_dimension_name_and_value(dimension, index):
    all_keys = dimension.keys()
    if len(all_keys) == 1:
        dimension_name = [key for key in all_keys][0]
        dimension_values = dimension[dimension_name]
        # We need to enrich only table data. Static values like IF-MIB::ifNumber.0 won't be enriched (it doesn't
        # make sense for those)
        if index >= 0 and index < len(dimension_values):
            return dimension_name, dimension_values[index]
    return None, None


class MibEnricher:
    def __init__(self, mib_static_data_collection):
        self._mib_static_data_collection = mib_static_data_collection
        # self._index_number_name = mib_static_data_collection_additional
        # self.dimensions_fields = self.__collect_if_mib_fields(
        #     mib_static_data_collection_exisiting, mib_static_data_collection_additional
        # )

    def get_by_oid(self, oid_family):
        if oid_family not in self._mib_static_data_collection:
            return {}
        return self._mib_static_data_collection[oid_family]

    def get_by_oid_and_type(self, oid_family, type):
        oid_record = self.get_by_oid(oid_family)
        if not oid_record:
            oid_record = self.get_by_oid(oid_family.split(".")[1])
        return oid_record.get(type, {})

    #
    # def __collect_if_mib_fields(self, mib_static_data_collection, mib_static_data_collection_additional):
    #     fields = []
    #     if not mib_static_data_collection:
    #         return []
    #     for el in mib_static_data_collection:
    #         fields += list(el.keys())
    #     if mib_static_data_collection_additional:
    #         fields += list(mib_static_data_collection_additional.values())
    #         # for oidFamily in mib_static_data_collection_additional:
    #         #     fields += list(mib_static_data_collection_additional[oidFamily].values())
    #     logger.info(f"_mib_static_data_collection: {mib_static_data_collection}")
    #     logger.info(f"__collect_if_mib_fields: {fields}")
    #     return fields

    def __enrich_if_mib_existing(self, metric_name):
        result = []
        if metric_name and metric_name.startswith(InterfaceMib.IF_MIB_METRIC_PREFIX):
            if self._mib_static_data_collection:
                if_mib_record = self.get_by_oid_and_type(
                    InterfaceMib.IF_MIB_METRIC_PREFIX, "existingVarBinds"
                )
                for dimension in if_mib_record:
                    index = extract_current_index_from_metric(metric_name)
                    (
                        dimension_name,
                        dimension_value,
                    ) = extract_dimension_name_and_value(dimension, index)
                    if dimension_name:
                        result.append({dimension_name: dimension_value})
        return result

    def __enrich_if_mib_additional(self, metric_name):
        for oid_family in self._mib_static_data_collection.keys():
            if oid_family in metric_name:
                index = extract_current_index_from_metric(metric_name) + 1
                index_field = self.get_by_oid_and_type(
                    oid_family, "additionalVarBinds"
                )["indexNum"]
                return [{index_field: index}]
        return []

    def append_additional_dimensions(self, translated_var_bind):
        if translated_var_bind:
            metric_name = translated_var_bind[InterfaceMib.METRIC_NAME_KEY]
            additional_if_mib_dimensions = []
            fields_list = []
            if self._mib_static_data_collection:
                additional_if_mib_dimensions += self.__enrich_if_mib_existing(
                    metric_name
                )
                additional_if_mib_dimensions += self.__enrich_if_mib_additional(
                    metric_name
                )
            for more_data in additional_if_mib_dimensions:
                translated_var_bind.update(more_data)
                fields_list += list(more_data.keys())
            return fields_list
        else:
            logger.warning("None translated var binds, enrichment process will be skip")
