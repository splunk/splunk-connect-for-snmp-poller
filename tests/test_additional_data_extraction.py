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

        fields = {
            "metric_name:sc4snmp.TCP-MIB.tcpConnLocalPort_192_168_0_1_161_127_0_0_1_5": "1111"
        }

        parsed_index = {
            "test1": "value1",
            "test2": "value2",
        }

        extract_additional_properties(
            fields,
            "sc4snmp.TCP-MIB.tcpConnLocalPort_192_168_0_1_161_127_0_0_1_5",
            "1111",
            parsed_index,
        )

        self.assertEqual(fields["test1"], "value1")
        self.assertEqual(fields["test2"], "value2")
