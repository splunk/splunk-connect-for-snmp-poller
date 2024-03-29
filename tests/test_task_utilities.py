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
from unittest.mock import MagicMock, patch

from pysnmp.smi.rfc1902 import ObjectIdentity

from splunk_connect_for_snmp_poller.manager.task_utilities import (
    _sort_walk_data,
    is_metric_data,
    is_oid,
    mib_string_handler,
    parse_port,
    process_one_time_flag,
)
from splunk_connect_for_snmp_poller.utilities import OnetimeFlag


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

    def test__sort_walk_data_metric(self):
        varbind = '{"metric_name": "sc4snmp.IF-MIB.ifIndex_1", "_value": "1", "metric_type": "Integer"}'
        varbind_dict = {
            "metric_name": "sc4snmp.IF-MIB.ifIndex_1",
            "_value": "1",
            "metric_type": "Integer",
        }
        is_metric = True
        merged_result_metric, merged_result_non_metric, merged_result = [], [], []
        result = _sort_walk_data(
            is_metric,
            merged_result_metric,
            merged_result_non_metric,
            merged_result,
            varbind,
        )
        self.assertEqual(merged_result_metric, [varbind])
        self.assertEqual(merged_result, [varbind_dict])
        self.assertEqual(merged_result_non_metric, [])
        self.assertEqual(result, varbind)

    def test__sort_walk_data_non_metric(self):
        varbind = '{"metric":"{\\"metric_name\\": \\"sc4snmp.IF-MIB.ifDescr_1\\", \\"_value\\": \\"lo\\", \\"metric_type\\": \\"OctetString\\"}","metric_name":"sc4snmp.IF-MIB.ifDescr_1","non_metric":"oid-type1=\\"ObjectIdentity\\" value1-type=\\"OctetString\\" 1.3.6.1.2.1.2.2.1.2.1=\\"lo\\" value1=\\"lo\\" IF-MIB::ifDescr.1=\\"lo\\" "}'  # noqa: E501
        expected_result = """oid-type1="ObjectIdentity" value1-type="OctetString" 1.3.6.1.2.1.2.2.1.2.1="lo" value1="lo" IF-MIB::ifDescr.1="lo" """  # noqa: E501
        varbind_metric_dict = {
            "metric_name": "sc4snmp.IF-MIB.ifDescr_1",
            "_value": "lo",
            "metric_type": "OctetString",
        }
        is_metric = False
        merged_result_metric, merged_result_non_metric, merged_result = [], [], []
        result = _sort_walk_data(
            is_metric,
            merged_result_metric,
            merged_result_non_metric,
            merged_result,
            varbind,
        )
        self.assertEqual(merged_result_metric, [])
        self.assertEqual(merged_result, [varbind_metric_dict])
        self.assertEqual(merged_result_non_metric, [varbind])
        self.assertEqual(result, expected_result)

    def test__sort_walk_data_without_mib_server_metric(self):
        varbind = '{"metric_name": "sc4snmp.SNMPv2-SMI.mib-2_2_2_1_10_2", "_value": "137003294"}'
        varbind_metric_dict = {
            "metric_name": "sc4snmp.SNMPv2-SMI.mib-2_2_2_1_10_2",
            "_value": "137003294",
        }
        is_metric = True
        merged_result_metric, merged_result_non_metric, merged_result = [], [], []
        result = _sort_walk_data(
            is_metric,
            merged_result_metric,
            merged_result_non_metric,
            merged_result,
            varbind,
        )
        self.assertEqual(merged_result_metric, [varbind])
        self.assertEqual(merged_result, [varbind_metric_dict])
        self.assertEqual(merged_result_non_metric, [])
        self.assertEqual(result, varbind)

    def test__sort_walk_data_without_mib_server_non_metric(self):
        varbind = '{"metric": {"metric_name": "SNMPv2-SMI::mib-2.2.2.1.2.1", "_value": "lo"}, "non_metric": "SNMPv2-SMI::mib-2.2.2.1.2.1=lo"}'  # noqa: E501
        varbind_metric_dict = {
            "metric_name": "SNMPv2-SMI::mib-2.2.2.1.2.1",
            "_value": "lo",
        }
        expected_result = "SNMPv2-SMI::mib-2.2.2.1.2.1=lo"
        is_metric = False
        merged_result_metric, merged_result_non_metric, merged_result = [], [], []
        result = _sort_walk_data(
            is_metric,
            merged_result_metric,
            merged_result_non_metric,
            merged_result,
            varbind,
        )
        self.assertEqual(merged_result_metric, [])
        self.assertEqual(merged_result, [varbind_metric_dict])
        self.assertEqual(merged_result_non_metric, [varbind])
        self.assertEqual(result, expected_result)

    def test_is_oid_asterisk(self):
        oid = "1.3.6.1.2.1.2.2.1.1.*"
        self.assertTrue(is_oid(oid))

    def test_is_oid(self):
        oid = "1.3.6.1.2.1"
        self.assertTrue(is_oid(oid))

    def test_is_oid_multinumber(self):
        oid = "1.3.6.1.2.195.218.254.105.56134.205.188.8.43.5190"
        self.assertTrue(is_oid(oid))

    def test_is_oid_profile(self):
        oid = "router"
        self.assertFalse(is_oid(oid))

    def test_is_oid_profile_with_dot(self):
        oid = "router.12"
        self.assertFalse(is_oid(oid))

    def test_process_one_time_flag_first_walk_error(self):
        mongo = MagicMock()
        ir = MagicMock()
        mongo.add_onetime_walk_result.return_value = "add_onetime"
        mongo.delete_onetime_walk_result.return_value = "delete_onetime"
        process_one_time_flag(
            OnetimeFlag.FIRST_WALK.value, True, mongo, "127.0.0.1:161", ir
        )
        self.assertTrue(mongo.add_onetime_walk_result.called)
        self.assertFalse(mongo.delete_onetime_walk_result.called)

    def test_process_one_time_first_walk_success(self):
        mongo = MagicMock()
        ir = MagicMock()
        mongo.add_onetime_walk_result.return_value = "add_onetime"
        mongo.delete_onetime_walk_result.return_value = "delete_onetime"
        process_one_time_flag(
            OnetimeFlag.FIRST_WALK.value, False, mongo, "127.0.0.1:161", ir
        )
        self.assertFalse(mongo.add_onetime_walk_result.called)
        self.assertFalse(mongo.delete_onetime_walk_result.called)

    def test_process_one_time_flag_after_failure_walk_error(self):
        mongo = MagicMock()
        ir = MagicMock()
        mongo.add_onetime_walk_result.return_value = "add_onetime"
        mongo.delete_onetime_walk_result.return_value = "delete_onetime"
        process_one_time_flag(
            OnetimeFlag.AFTER_FAIL.value, True, mongo, "127.0.0.1:161", ir
        )
        self.assertFalse(mongo.delete_onetime_walk_result.called)
        self.assertFalse(mongo.add_onetime_walk_result.called)

    def test_process_one_time_flag_after_failure_walk_success(self):
        mongo = MagicMock()
        ir = MagicMock()
        mongo.add_onetime_walk_result.return_value = "add_onetime"
        mongo.delete_onetime_walk_result.return_value = "delete_onetime"
        process_one_time_flag(
            OnetimeFlag.AFTER_FAIL.value, False, mongo, "127.0.0.1:161", ir
        )
        self.assertTrue(mongo.delete_onetime_walk_result.called)
        self.assertFalse(mongo.add_onetime_walk_result.called)

    def test_mib_string_handler_two_element(self):
        with patch(
            "splunk_connect_for_snmp_poller.manager.task_utilities.translate_list_to_oid"
        ) as mock:
            returned = MagicMock()
            returned.__class__ = ObjectIdentity
            mock.return_value = returned
            oid = mib_string_handler([["IF-MIB", "ifMtu"]])
        self.assertEqual(len(oid.bulk), 1)
        self.assertEqual(len(oid.get), 0)

    def test_mib_string_handler_three_elements(self):
        with patch(
            "splunk_connect_for_snmp_poller.manager.task_utilities.translate_list_to_oid"
        ) as mock:
            returned = MagicMock()
            returned.__class__ = ObjectIdentity
            mock.return_value = returned
            oid = mib_string_handler([["IF-MIB", "ifMtu", 1]])
        self.assertEqual(len(oid.get), 1)
        self.assertEqual(len(oid.bulk), 0)

    def test_mib_string_handler_four_elements(self):
        with patch(
            "splunk_connect_for_snmp_poller.manager.task_utilities.translate_list_to_oid"
        ) as mock:
            returned = MagicMock()
            returned.__class__ = ObjectIdentity
            mock.return_value = returned
            oid = mib_string_handler([["IF-MIB", "ifMtu", 1, ""]])
        self.assertEqual(len(oid.get), 0)
        self.assertEqual(len(oid.bulk), 0)
