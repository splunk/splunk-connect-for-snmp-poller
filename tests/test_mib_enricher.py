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

from splunk_connect_for_snmp_poller.manager.static.mib_enricher import MibEnricher

mib_static_data_coll = [
    {"interface_index": ["1", "2"]},
    {"interface_desc": ["lo", "eth0"]},
]


class TestMibEnricher(TestCase):
    def test_process_one_none_input_parameter(self):
        MibEnricher(mib_static_data_coll).append_additional_dimensions(None)

    def test_process_one_valid_no_if_mib_entry(self):
        translated_metric = {
            "metric_name": "sc4snmp.TCP-MIB::tcpInErrs_0",
            "_value": "3",
            "metric_type": "Counter32",
        }
        enricher = MibEnricher(mib_static_data_coll)
        enricher.append_additional_dimensions(translated_metric)
        self.assertTrue(len(translated_metric) == 3)
        self.assertEqual(
            set(["metric_name", "_value", "metric_type"]), translated_metric.keys()
        )

    def test_process_one_valid_if_mib_entry_iwith_zero_index(self):
        translated_metric = {
            "metric_name": "sc4snmp.IF-MIB::ifNumber.0",
            "_value": "2",
            "metric_type": "Integer",
        }
        enricher = MibEnricher(mib_static_data_coll)
        enricher.append_additional_dimensions(translated_metric)
        self.assertTrue(len(translated_metric) == 3)
        self.assertEqual(
            set(["metric_name", "_value", "metric_type"]), translated_metric.keys()
        )

    def test_process_one_valid_if_mib_entry_without_proper_mongo_static_data(self):
        translated_metric = {
            "metric_name": "sc4snmp.IF-MIB.ifIndex_2",
            "_value": "2",
            "metric_type": "Integer",
        }
        enricher = MibEnricher(None)
        enricher.append_additional_dimensions(translated_metric)
        self.assertTrue(len(translated_metric) == 3)
        self.assertEqual(
            set(["metric_name", "_value", "metric_type"]), translated_metric.keys()
        )

    def test_process_one_valid_if_mib_entry(self):
        translated_metric = {
            "metric_name": "sc4snmp.IF-MIB.ifIndex_2",
            "_value": "2",
            "metric_type": "Integer",
        }
        enricher = MibEnricher(mib_static_data_coll)
        enricher.append_additional_dimensions(translated_metric)
        self.assertTrue("interface_index" in translated_metric)
        self.assertTrue("interface_desc" in translated_metric)
