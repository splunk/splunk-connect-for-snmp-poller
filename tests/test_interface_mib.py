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
import os
from unittest import TestCase

from splunk_connect_for_snmp_poller.manager.realtime.interface_mib import (
    InterfaceMib,
)
from tests.test_utils import load_test_data

logger = logging.getLogger(__name__)


def file_data_path(data_file_name):
    current_dir = os.getcwd()
    relative_data_file_path = os.path.join("mib_walk_data", data_file_name)
    if current_dir.endswith("tests"):
        file_path = os.path.join(current_dir, relative_data_file_path)
    else:
        file_path = os.path.join(current_dir, "tests", relative_data_file_path)
    return file_path


class TestInterfaceMib(TestCase):
    def test_loaded_walk_data_for_if_mib(self):
        file_path = file_data_path("if_mib_walk.json")
        if_mibs = load_test_data(file_path)
        self.assertIsNotNone(if_mibs)

        mibs = InterfaceMib(if_mibs)

        logger.info(f"Total number of network interfaces: {mibs.network_interfaces()}")
        self.assertGreater(mibs.network_interfaces(), 0)

        interface_names = mibs.network_interface_names()
        logger.info(f"Interfaces: {interface_names}")
        self.assertIsNotNone(interface_names)
        self.assertEqual(interface_names, ["lo", "eth0"])

        inteface_indexes = mibs.network_indexes()
        logger.info(f"Interfaces: {inteface_indexes}")
        self.assertIsNotNone(inteface_indexes)
        self.assertEqual(inteface_indexes, ["1", "2"])

        self.assertTrue(mibs.has_consistent_data())

    def test_walk_data_with_wrong_number_of_interfaces(self):
        for invalid_data_file in [
            "if_mib_walk_invalid_networks.json",
            "if_mib_walk_invalid_indexes.json",
        ]:
            file_path = file_data_path(invalid_data_file)
            if_mibs = load_test_data(file_path)
            self.assertIsNotNone(if_mibs)

            mibs = InterfaceMib(if_mibs)
            self.assertFalse(mibs.has_consistent_data())
            totals = mibs.network_interfaces()
            indexes = len(mibs.network_indexes())
            names = len(mibs.network_interface_names())
            logger.info(
                f"Inconsistent data for {invalid_data_file} totals = {totals}, indexes = {indexes}, names = {names}"
            )
