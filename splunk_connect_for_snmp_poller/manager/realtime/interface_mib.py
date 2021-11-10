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
from operator import itemgetter


# See http://www.net-snmp.org/docs/mibs/interfaces.html for additional implementation details
def extract_if_mib_only(translated_walk_result):
    return filter(
        lambda translation: all(
            key in translation
            for key in (
                InterfaceMib.METRIC_NAME_KEY,
                InterfaceMib.METRIC_VALUE_KEY,
                InterfaceMib.METRIC_TYPE_KEY,
                InterfaceMib.METRIC_PARSED_INDEX_KEY,
            )
        )
        and translation[InterfaceMib.METRIC_NAME_KEY].startswith(
            InterfaceMib.IF_MIB_METRIC_PREFIX
        ),
        translated_walk_result,
    )


class InterfaceMib:
    METRIC_NAME_KEY = "metric_name"
    METRIC_VALUE_KEY = "_value"
    METRIC_TYPE_KEY = "metric_type"
    METRIC_PARSED_INDEX_KEY = "parsed_index"
    METRIC_IF_INDEX_KEY = "ifIndex"
    IF_MIB_METRIC_PREFIX = "sc4snmp.IF-MIB."
    IF_MIB_DATA_MONGO_IDENTIFIER = "IF-MIB"

    def __init__(self, if_mib_metric_walk_data):
        self._if_mib_walk_data = extract_if_mib_only(if_mib_metric_walk_data)
        self._full_dictionary = self.__build_in_memory_dictionary()

    def unprocessed_if_mib_data(self):
        return self._if_mib_walk_data

    def __build_in_memory_dictionary(self):
        all_keys = {}
        for mib in self.unprocessed_if_mib_data():
            if mib[InterfaceMib.METRIC_NAME_KEY] not in all_keys:
                all_keys[mib[InterfaceMib.METRIC_NAME_KEY]] = []
            all_keys[mib[InterfaceMib.METRIC_NAME_KEY]].append(
                {
                    InterfaceMib.METRIC_VALUE_KEY: mib[InterfaceMib.METRIC_VALUE_KEY],
                    InterfaceMib.METRIC_TYPE_KEY: mib[InterfaceMib.METRIC_TYPE_KEY],
                    InterfaceMib.METRIC_PARSED_INDEX_KEY: self.__get_ifindex(
                        mib[InterfaceMib.METRIC_PARSED_INDEX_KEY]
                    ),
                }
            )
            sorted(
                all_keys[mib[InterfaceMib.METRIC_NAME_KEY]],
                key=itemgetter(InterfaceMib.METRIC_PARSED_INDEX_KEY),
            )
        return all_keys

    def __get_ifindex(self, ifindex_dictionary):
        return ifindex_dictionary[InterfaceMib.METRIC_IF_INDEX_KEY]

    def _return_number_of_interfaces(self):
        for value_list in self._full_dictionary.values():
            return len(value_list)

    def __extract_single_field_as_list(self, base_mib_metric_name):
        all_indexes = []
        if base_mib_metric_name in self._full_dictionary:
            for el in self._full_dictionary[base_mib_metric_name]:
                all_indexes.append(el[InterfaceMib.METRIC_VALUE_KEY])
        return all_indexes

    def extract_custom_field(self, snmp_field_name):
        return self.__extract_single_field_as_list(snmp_field_name)
