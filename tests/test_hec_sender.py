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

from splunk_connect_for_snmp_poller.manager.hec_sender import (
    _enrich_event_data,
    _enrich_metric_data,
)
from splunk_connect_for_snmp_poller.manager.static.mib_enricher import MibEnricher

_MibEnricher = MibEnricher(
    {
        "IF-MIB": {
            "existingVarBinds": [
                {"interface_index": ["1", "2", "3"]},
                {"interface_desc": ["lo", "eth0", "eth1"]},
            ]
        }
    }
)


class TestHecSender(TestCase):
    def test__enrich_metric_data_index_0(self):
        fields = {"metric_name:sc4snmp.IF-MIB.ifNumber_0": "2"}
        fields_initial = fields.copy()
        variables_binds = {
            "metric_name": "sc4snmp.IF-MIB.ifNumber_0",
            "_value": "2",
            "metric_type": "Integer",
        }
        variables_binds_initial = variables_binds.copy()
        _enrich_metric_data(_MibEnricher, variables_binds, fields)
        self.assertEqual(variables_binds, variables_binds_initial)
        self.assertEqual(fields, fields_initial)

    def test__enrich_metric_data_index_1(self):
        fields = {
            "metric_name:sc4snmp.IF-MIB.ifIndex_1": "1",
            "interface_desc": "lo",
            "interface_index": "1",
        }
        fields_initial = {"metric_name:sc4snmp.IF-MIB.ifIndex_1": "1"}
        variables_binds = {
            "metric_name": "sc4snmp.IF-MIB.ifIndex_1",
            "_value": "1",
            "metric_type": "Integer",
            "interface_desc": "lo",
            "interface_index": "1",
        }
        variables_binds_initial = {
            "metric_name": "sc4snmp.IF-MIB.ifIndex_1",
            "_value": "1",
            "metric_type": "Integer",
        }
        _enrich_metric_data(_MibEnricher, variables_binds_initial, fields_initial)
        self.assertEqual(variables_binds, variables_binds_initial)
        self.assertEqual(fields, fields_initial)

    def test__enrich_metric_data_index_2(self):
        fields = {
            "metric_name:sc4snmp.IF-MIB.ifIndex_2": "2",
            "interface_desc": "eth0",
            "interface_index": "2",
        }
        fields_initial = {"metric_name:sc4snmp.IF-MIB.ifIndex_2": "2"}
        variables_binds = {
            "metric_name": "sc4snmp.IF-MIB.ifIndex_2",
            "_value": "2",
            "metric_type": "Integer",
            "interface_desc": "eth0",
            "interface_index": "2",
        }
        variables_binds_initial = {
            "metric_name": "sc4snmp.IF-MIB.ifIndex_2",
            "_value": "2",
            "metric_type": "Integer",
        }
        _enrich_metric_data(_MibEnricher, variables_binds_initial, fields_initial)
        self.assertEqual(variables_binds, variables_binds_initial)
        self.assertEqual(fields, fields_initial)

    def test__enrich_metric_data_index_3(self):
        fields = {
            "metric_name:sc4snmp.IF-MIB.ifIndex_3": "3",
            "interface_desc": "eth1",
            "interface_index": "3",
        }
        fields_initial = {"metric_name:sc4snmp.IF-MIB.ifIndex_3": "3"}
        variables_binds = {
            "metric_name": "sc4snmp.IF-MIB.ifIndex_3",
            "_value": "3",
            "metric_type": "Integer",
            "interface_desc": "eth1",
            "interface_index": "3",
        }
        variables_binds_initial = {
            "metric_name": "sc4snmp.IF-MIB.ifIndex_3",
            "_value": "3",
            "metric_type": "Integer",
        }
        _enrich_metric_data(_MibEnricher, variables_binds_initial, fields_initial)
        self.assertEqual(variables_binds, variables_binds_initial)
        self.assertEqual(fields, fields_initial)

    def test__enrich_event_data_index_1(self):
        variables_binds = {
            "metric": '{"metric_name": "sc4snmp.IF-MIB.ifDescr_1", "_value": "lo", '
            '"metric_type": "OctetString"}',
            "metric_name": "sc4snmp.IF-MIB.ifDescr_1",
            "non_metric": 'oid-type1="ObjectIdentity" value1-type="OctetString" '
            '1.3.6.1.2.1.2.2.1.2.1="lo" value1="lo" IF-MIB::ifDescr.1="lo" ',
        }
        variables_binds_result = (
            'oid-type1="ObjectIdentity" value1-type="OctetString" 1.3.6.1.2.1.2.2.1.2.1="lo" '
            'value1="lo" IF-MIB::ifDescr.1="lo" interface_index="1" interface_desc="lo" '
        )
        variables_binds_processed = _enrich_event_data(_MibEnricher, variables_binds)
        self.assertEqual(variables_binds_processed, variables_binds_result)

    def test__enrich_event_data_index_2(self):
        variables_binds = {
            "metric": '{"metric_name": "sc4snmp.IF-MIB.ifDescr_2", "_value": "eth0", '
            '"metric_type": "OctetString"}',
            "metric_name": "sc4snmp.IF-MIB.ifDescr_2",
            "non_metric": 'oid-type1="ObjectIdentity" value1-type="OctetString" '
            '1.3.6.1.2.1.2.2.1.2.1="lo" value1="eth0" IF-MIB::ifDescr.2="eth0" ',
        }
        variables_binds_result = (
            'oid-type1="ObjectIdentity" value1-type="OctetString" 1.3.6.1.2.1.2.2.1.2.1="lo" '
            'value1="eth0" IF-MIB::ifDescr.2="eth0" interface_index="2" interface_desc="eth0" '
        )
        variables_binds_processed = _enrich_event_data(_MibEnricher, variables_binds)
        self.assertEqual(variables_binds_processed, variables_binds_result)

    def test__enrich_event_data_index_3(self):
        variables_binds = {
            "metric": '{"metric_name": "sc4snmp.IF-MIB.ifDescr_3", "_value": "eth1", '
            '"metric_type": "OctetString"}',
            "metric_name": "sc4snmp.IF-MIB.ifDescr_3",
            "non_metric": 'oid-type1="ObjectIdentity" value1-type="OctetString" '
            '1.3.6.1.2.1.2.2.1.2.1="lo" value1="eth1" IF-MIB::ifDescr.3="eth1" ',
        }
        variables_binds_result = (
            'oid-type1="ObjectIdentity" value1-type="OctetString" 1.3.6.1.2.1.2.2.1.2.1="lo" '
            'value1="eth1" IF-MIB::ifDescr.3="eth1" interface_index="3" interface_desc="eth1" '
        )
        variables_binds_processed = _enrich_event_data(_MibEnricher, variables_binds)
        self.assertEqual(variables_binds_processed, variables_binds_result)
