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
from unittest import TestCase

from splunk_connect_for_snmp_poller.manager.realtime.interface_mib import InterfaceMib
from splunk_connect_for_snmp_poller.manager.static.interface_mib_utililities import (
    extract_network_interface_data_from_config,
    extract_network_interface_data_from_walk,
    get_additional_varbinds,
)
from tests.test_config_input_data import (
    parsed_config_correct,
    parsed_config_correct_one_non_existing_field,
    parsed_config_correct_three_fields,
    parsed_config_duplicate_keys,
    parsed_config_family_with_error,
    parsed_config_if_mib_with_error,
    parsed_config_if_mib_without_elements,
    parsed_config_root_with_error,
    parsed_config_with_additional_varbinds_ifmib,
    parsed_config_with_additional_varbinds_snmp_mib,
)
from tests.test_utils import file_data_path, load_test_data

logger = logging.getLogger(__name__)


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
                "oid_name": f"{InterfaceMib.IF_MIB_METRIC_PREFIX}ifIndex_",
                "splunk_dimension_name": "interface_index",
            },
            {
                "oid_name": f"{InterfaceMib.IF_MIB_METRIC_PREFIX}ifDescr_",
                "splunk_dimension_name": "interface_desc",
            },
        ]
        self.assertEqual(result, expected_result)

    def test_duplicate_keys(self):
        result = extract_network_interface_data_from_config(
            parsed_config_duplicate_keys
        )
        self.assertTrue(len(result) == 3)
        expected_result = [
            {
                "oid_name": "sc4snmp.IF-MIB.ifIndex_",
                "splunk_dimension_name": "interface_index",
            },
            {
                "oid_name": "sc4snmp.IF-MIB.ifIndex_",
                "splunk_dimension_name": "interface_index",
            },
            {
                "oid_name": "sc4snmp.IF-MIB.ifIndex_",
                "splunk_dimension_name": "interface_index_2",
            },
        ]
        self.assertEqual(result, expected_result)


class ExtractEnricherDataFromSNMPWalkTest(TestCase):
    def test_basic_integration(self):
        file_path = file_data_path("if_mib_walk.json")
        if_mibs = load_test_data(file_path)
        self.assertIsNotNone(if_mibs)

        result = extract_network_interface_data_from_walk(
            parsed_config_correct_three_fields, if_mibs
        )
        self.assertTrue(len(result) == 3)
        expected_result = [
            {"interface_index": ["1", "2"]},
            {"interface_desc": ["lo", "eth0"]},
            {"total_in_packets": ["51491148", "108703537"]},
        ]
        self.assertEqual(result, expected_result)

    def test_basic_integration_one_non_existing_field(self):
        file_path = file_data_path("if_mib_walk.json")
        if_mibs = load_test_data(file_path)
        self.assertIsNotNone(if_mibs)

        result = extract_network_interface_data_from_walk(
            parsed_config_correct_one_non_existing_field, if_mibs
        )
        self.assertTrue(len(result) == 2)
        expected_result = [
            {"interface_index": ["1", "2"]},
            {"interface_desc": ["lo", "eth0"]},
        ]
        self.assertEqual(result, expected_result)


class ExtractAdditionalVarbinds(TestCase):
    def test_additional_varbinds_ifmib(self):
        file_path = file_data_path("if_mib_walk.json")
        if_mibs = load_test_data(file_path)
        self.assertIsNotNone(if_mibs)
        result = get_additional_varbinds(parsed_config_with_additional_varbinds_ifmib)
        self.assertTrue(len(result) == 1)
        expected_result = {"IF-MIB": {"indexNum": "index_num"}}

        self.assertEqual(result, expected_result)

    def test_additional_varbinds_snmp_mib(self):
        file_path = file_data_path("if_mib_walk.json")
        if_mibs = load_test_data(file_path)
        self.assertIsNotNone(if_mibs)
        result = get_additional_varbinds(
            parsed_config_with_additional_varbinds_snmp_mib
        )
        self.assertTrue(len(result) == 1)
        expected_result = {
            "IF-MIB": {"indexNum": "index_num"},
            "SNMPv2-MIB": {"indexNum": "index_number"},
        }

        self.assertEqual(result, expected_result)

    def test_additional_varbinds_none(self):
        file_path = file_data_path("if_mib_walk.json")
        if_mibs = load_test_data(file_path)
        self.assertIsNotNone(if_mibs)
        result = get_additional_varbinds(parsed_config_correct)
        self.assertTrue(len(result) == 1)
        expected_result = {"IF-MIB": {}}

        self.assertEqual(result, expected_result)
