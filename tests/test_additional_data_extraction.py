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
    extract_additional_properties,
)


class TestAdditionalDataExtraction(TestCase):
    def test_data_extraction(self):
        server_config = {
            "enricher": {
                "oidFamily": {
                    "TCP-MIB": {
                        "additionalVarBinds": [
                            {
                                "regex": "(?P<IP_one>[0-9]+_[0-9]+_[0-9]+_[0-9]+)_(?P<port>[0-9]+)_(?P<IP_two>[0-9]+_[0-9]+_[0-9]+_[0-9]+)_(?P<index_number>[0-9]+)",  # noqa: E501
                            }
                        ]
                    },
                    "IF-MIB": {
                        "existingVarBinds": [
                            {"ifDescr": "interface_desc"},
                            {"ifPhysAddress": "MAC_address"},
                        ],
                    },
                    "UDP-MIB": {
                        "additionalVarBinds": [
                            {
                                "regex": '(?P<protocol_version_one>ipv4)_"(?P<IP_one>[0-9]+_[0-9]+_[0-9]+_[0-9]+)"_(?P<port_one>[0-9]+)_(?P<protocol_version_two>ipv4)_"(?P<IP_two>[0-9]+_[0-9]+_[0-9]+_[0-9]+)"_(?P<index_number>[0-9]+)_(?P<port_two>[0-9]+)',  # noqa: E501
                            }
                        ]
                    },
                }
            }
        }

        fields = {
            "metric_name:sc4snmp.TCP-MIB.tcpConnLocalPort_192_168_0_1_161_127_0_0_1_5": "1111"
        }
        fields2 = {"metric_name:sc4snmp.IF-MIB.ifInErrors_2_1_asdad_23": "173127"}
        fields3 = {
            'metric_name:sc4snmp.UDP-MIB.udpEndpointProcess_ipv4_"0_0_0_0"_111_ipv4_"0_0_0_0"_0_13348': "123"
        }

        extract_additional_properties(
            fields,
            "sc4snmp.TCP-MIB.tcpConnLocalPort_192_168_0_1_161_127_0_0_1_5",
            "1111",
            server_config,
        )

        extract_additional_properties(
            fields2, "sc4snmp.IF-MIB.ifInErrors_2_1_asdad_23", "173127", server_config
        )

        extract_additional_properties(
            fields3,
            'sc4snmp.UDP-MIB.udpEndpointProcess_ipv4_"0_0_0_0"_111_ipv4_"0_0_0_0"_0_13348',
            "123",
            server_config,
        )

        self.assertEqual(fields["IP_one"], "192.168.0.1")
        self.assertEqual(fields["port"], "161")
        self.assertEqual(fields["IP_two"], "127.0.0.1")
        self.assertEqual(fields["index_number"], "5")

        self.assertEqual(fields2["index_number"], "23")

        self.assertEqual(fields3["protocol_version_one"], "ipv4")
        self.assertEqual(fields3["IP_one"], "0.0.0.0")
        self.assertEqual(fields3["port_one"], "111")
        self.assertEqual(fields3["protocol_version_two"], "ipv4")
        self.assertEqual(fields3["IP_two"], "0.0.0.0")
        self.assertEqual(fields3["index_number"], "0")
        self.assertEqual(fields3["port_two"], "13348")