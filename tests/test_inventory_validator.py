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

from splunk_connect_for_snmp_poller.manager.validator.inventory_validator import (
    is_valid_inventory_line_from_dict,
    should_process_inventory_line,
)
from tests.static_inventory_test_data import InventoryLineBuilder

logger = logging.getLogger(__name__)

INVENTORY_COMPONENTS_PER_LINE = 5


def is_valid_inventory_line(line):
    logger.debug(f"Validating [{line}]")
    if not line or not line.strip():
        return False

    components = [component.strip() for component in line.split(",")]
    logger.debug(f"Components: {components}")
    if len(components) != INVENTORY_COMPONENTS_PER_LINE:
        return False

    return is_valid_inventory_line_from_dict(
        components[0], components[1], components[2], components[3], components[4]
    )


class TestInventoryLine(TestCase):
    def test_should_process_inventory_line(self):
        for line in InventoryLineBuilder().skipped_or_empty_configurations():
            logger.info(f"Checking <{line}>")
            self.assertFalse(should_process_inventory_line(line))

    def test_valid_inventory_line(self):
        for line in InventoryLineBuilder().valid_inventory_lines():
            logger.info(f"Checking <{line}>")
            self.assertTrue(is_valid_inventory_line(line))

    def test_invalid_host_names(self):
        for line in InventoryLineBuilder().invalid_host_names():
            logger.info(f"Invalid hostname and/or port: {line}")
            self.assertFalse(is_valid_inventory_line(line))

    def test_invalid_snmp_version(self):
        for line in InventoryLineBuilder().invalid_snmp_versions():
            logger.info(f"Invalid SNMP protocol version: {line}")
            self.assertFalse(is_valid_inventory_line(line))
