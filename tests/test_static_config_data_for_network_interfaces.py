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
from unittest import TestCase

from splunk_connect_for_snmp_poller.manager.realtime.interface_mib import InterfaceMib
from splunk_connect_for_snmp_poller.manager.static.interface_mib_utililities import (
    extract_network_interface_data_from_config,
)

parsed_config_root_with_error = {
    "enricher_with_error": {
        "oidFamily": {
            "IF-MIB": [
                {"ifIndex": "interface_index"},
                {"ifDescr": "interface_desc"},
            ]
        }
    }
}

parsed_config_family_with_error = {
    "enricher": {
        "oidFamily_with_error": {
            "IF-MIB": [
                {"ifIndex": "interface_index"},
                {"ifDescr": "interface_desc"},
            ]
        }
    }
}

parsed_config_if_mib_with_error = {
    "enricher": {
        "oidFamily": {
            "IF-MIB_with_error": [
                {"ifIndex": "interface_index"},
                {"ifDescr": "interface_desc"},
            ]
        }
    }
}

parsed_config_if_mib_without_elements = {"enricher": {"oidFamily": {"IF-MIB": []}}}

parsed_config_correct = {
    "enricher": {
        "oidFamily": {
            "IF-MIB": [
                {"ifIndex": "interface_index"},
                {"ifDescr": "interface_desc"},
            ]
        }
    }
}


class ExtractEnricherDataFromConfigTest(TestCase):
    def test_config_does_not_exist(self):
        result = extract_network_interface_data_from_config(None)
        self.assertIsNotNone(result)
        self.assertTrue(len(result) == 0)

    def test_config_does_not_have_the_required_key(self):
        for test_config in (
            parsed_config_root_with_error,
            parsed_config_family_with_error,
            parsed_config_if_mib_with_error,
            parsed_config_if_mib_without_elements,
        ):
            result = extract_network_interface_data_from_config(test_config)
            self.assertTrue(len(result) == 0)

    def test_correct_config(self):
        result = extract_network_interface_data_from_config(parsed_config_correct)
        self.assertTrue(len(result) == 2)
        expected_result = [
            {
                "oid_name": f"{InterfaceMib.IF_MIB_METRIC_SUFFIX}ifIndex",
                "splunk_dimension_name": "interface_index",
            },
            {
                "oid_name": f"{InterfaceMib.IF_MIB_METRIC_SUFFIX}ifDescr",
                "splunk_dimension_name": "interface_desc",
            },
        ]
        self.assertEqual(result, expected_result)
