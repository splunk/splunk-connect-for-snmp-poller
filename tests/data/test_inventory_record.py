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

from splunk_connect_for_snmp_poller.manager.data.inventory_record import InventoryRecord

logger = logging.getLogger(__name__)


class TestInventoryRecord(TestCase):
    ir = InventoryRecord(
        "test_host", "test_version", "test_public", "test_profile", "10"
    )

    def test_inventory_record_to_json(self):
        """
        Test that checks if InventoryRecord correctly parses to json
        """
        ir = InventoryRecord(
            "test_host", "test_version", "test_public", "test_profile", "10"
        )
        expected_str = (
            '{"host": "test_host", "version": "test_version", '
            '"community": "test_public", "profile": "test_profile",'
            ' "frequency_str": "10"}'
        )

        ir_to_json = ir.to_json()

        self.assertEqual(expected_str, ir_to_json)

    def test_json_to_inventory(self):
        """
        Test that checks if json correctly loads to InventoryRecord
        """
        ir = InventoryRecord(
            "test_host", "test_version", "test_public", "test_profile", "10"
        )
        ir_to_json = ir.to_json()

        record_from_json = InventoryRecord.from_json(ir_to_json)

        self.assertEqual(ir, record_from_json)

    def test_extending_dict_with_config_data(self):
        """
        Test that checks if fields are correctly extended with profile data
        """
        ir = InventoryRecord(
            "test_host", "test_version", "test_public", "test_profile", "10"
        )
        fields = {"key1": "value"}
        expected_fields = {"key1": "value", "profile": "test_profile"}
        additional_fields = ["profile"]

        extended_fields = ir.extend_dict_with_provided_data(fields, additional_fields)

        self.assertDictEqual(expected_fields, extended_fields)

    def test_extending_dict_with_empty_data(self):
        """
        Test that checks if fields are not changed if additional fields are empty
        """
        ir = InventoryRecord(
            "test_host", "test_version", "test_public", "test_profile", "10"
        )
        fields = {"key1": "value"}
        additional_fields = None

        extended_fields = ir.extend_dict_with_provided_data(fields, additional_fields)

        self.assertDictEqual(fields, extended_fields)
