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

# See http://www.net-snmp.org/docs/mibs/interfaces.html for additional implementation details
def extract_if_mib_only(translated_walk_result):
    return filter(
        lambda translation: all(
            key in translation
            for key in (
                InterfaceMib.METRIC_NAME_KEY,
                InterfaceMib.METRIC_VALUE_KEY,
                InterfaceMib.METRIC_TYPE_KEY,
            )
        )
        and translation[InterfaceMib.METRIC_NAME_KEY].startswith(
            InterfaceMib.IF_MIB_METRIC_SUFFIX
        ),
        translated_walk_result,
    )


class InterfaceMib:
    METRIC_NAME_KEY = "metric_name"
    METRIC_VALUE_KEY = "_value"
    METRIC_TYPE_KEY = "metric_type"
    IF_MIB_METRIC_SUFFIX = "sc4snmp.IF-MIB."
    IF_MIB_IF_NUMBER = "sc4snmp.IF-MIB.ifNumber_0"
    IF_MIB_IF_INDEX_BASE = "sc4snmp.IF-MIB.ifIndex_"
    IF_MIB_IF_DESCR_BASE = "sc4snmp.IF-MIB.ifDescr_"

    def __init__(self, if_mib_walk_data):
        self._if_mib_walk_data = extract_if_mib_only(if_mib_walk_data)
        self._full_dictionary = self.__build_in_memory_dictionary()
        self._network_interfaces = self.__extract_number_of_network_interfaces()
        self._network_indexes = self.__extract_interface_indexes()
        self._network_interface_names = self.__extract_interface_names()

    def unprocessed_if_mib_data(self):
        return self._if_mib_walk_data

    def network_interfaces(self):
        return self._network_interfaces

    def network_indexes(self):
        return self._network_indexes

    def network_interface_names(self):
        return self._network_interface_names

    def has_consistent_data(self):
        return self.network_interfaces() == len(self.network_indexes()) and len(
            self.network_indexes()
        ) == len(self.network_interface_names())

    def __build_in_memory_dictionary(self):
        all_keys = dict()
        for mib in self.unprocessed_if_mib_data():
            all_keys[mib[InterfaceMib.METRIC_NAME_KEY]] = {
                InterfaceMib.METRIC_VALUE_KEY: mib[InterfaceMib.METRIC_VALUE_KEY],
                InterfaceMib.METRIC_TYPE_KEY: mib[InterfaceMib.METRIC_TYPE_KEY],
            }
        return all_keys

    def __extract_number_of_network_interfaces(self):
        if InterfaceMib.IF_MIB_IF_NUMBER in self._full_dictionary:
            if_number = self._full_dictionary[InterfaceMib.IF_MIB_IF_NUMBER]
            return int(if_number[InterfaceMib.METRIC_VALUE_KEY])
        else:
            return 0

    def __extract_single_field_as_list(self, base_mib_metric_name):
        all_indexes = []
        for index in range(0, self.network_interfaces()):
            current = base_mib_metric_name + str(index + 1)
            if current in self._full_dictionary:
                all_indexes.append(
                    self._full_dictionary[current][InterfaceMib.METRIC_VALUE_KEY]
                )
        return all_indexes

    def __extract_interface_indexes(self):
        return self.__extract_single_field_as_list(InterfaceMib.IF_MIB_IF_INDEX_BASE)

    def __extract_interface_names(self):
        return self.__extract_single_field_as_list(InterfaceMib.IF_MIB_IF_DESCR_BASE)

    def extract_custom_field(self, snmp_field_name):
        return self.__extract_single_field_as_list(snmp_field_name)
