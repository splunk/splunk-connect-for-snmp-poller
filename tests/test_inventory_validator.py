from unittest import TestCase
from splunk_connect_for_snmp_poller.manager.validator.inventory_validator import (
    should_process_inventory_line,
    is_valid_inventory_line,
    is_valid_host,
)
from tests.static_inventory_test_data import InventoryLineBuilder
import logging

logger = logging.getLogger(__name__)


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

    def test_invalid_community(self):
        for line in InventoryLineBuilder().invalid_communities():
            logger.info(f"Invalid SNMP protocol version: {line}")
            self.assertFalse(is_valid_inventory_line(line))
