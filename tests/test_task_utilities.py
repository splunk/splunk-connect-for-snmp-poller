#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#

from unittest import TestCase

from splunk_connect_for_snmp_poller.manager.task_utilities import (
    is_metric_data,
    parse_port,
)


class ObjectTypeMock:
    def __init__(self, value):
        self._value = value

    def prettyPrint(self):
        return self._value


class TestTaskUtilities(TestCase):
    def test_metric_for_integer(self):
        self.assertTrue(is_metric_data("1"))

    def test_metric_for_negative_integer(self):
        self.assertTrue(is_metric_data("-5"))

    def test_metric_for_float(self):
        self.assertTrue(is_metric_data("2.0"))

    def test_metric_for_negative_float(self):
        self.assertTrue(is_metric_data("-2.0"))

    def test_metric_for_zero(self):
        self.assertTrue(is_metric_data("0"))

    def test_metric_for_ip(self):
        self.assertFalse(is_metric_data("127.0.0.1"))

    def test_metric_for_string_with_numbers(self):
        self.assertFalse(is_metric_data("1.0 1"))

    def test_metric_for_string(self):
        self.assertFalse(is_metric_data("asdad"))

    def test_metric_for_exponential_value(self):
        self.assertTrue(is_metric_data("0.1e-10"))

    def test_metric_for_string_mix_of_letters_and_numbers(self):
        self.assertFalse(is_metric_data("0.1e a"))

    def test_port_parse_with_default_port(self):
        host, port = parse_port("192.168.0.13")
        self.assertEqual(host, "192.168.0.13")
        self.assertEqual(port, 161)

    def test_port_parse_with_specified_port(self):
        host, port = parse_port("192.168.0.13:765")
        self.assertEqual(host, "192.168.0.13")
        self.assertEqual(port, "765")
