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

from splunk_connect_for_snmp_poller.manager.profile_matching import (
    assign_profiles_to_device,
    extract_desc,
)
from splunk_connect_for_snmp_poller.manager.realtime.oid_constant import OidConstant


class TestProfileMatching(TestCase):
    def test_return_sysdescr(self):
        realtime_collection = {OidConstant.SYS_DESCR: {"value": "Linux Suse 1.2.3.4"}}

        descr = extract_desc(realtime_collection)
        self.assertEqual(2, len(descr))
        self.assertEqual("Linux Suse 1.2.3.4", descr[0])

    def test_return_sys_object_id(self):
        realtime_collection = {OidConstant.SYS_OBJECT_ID: {"value": "Some object ID"}}

        descr = extract_desc(realtime_collection)
        self.assertEqual(2, len(descr))
        self.assertEqual("Some object ID", descr[1])

    def test_return_both_when_both_values_are_present(self):
        realtime_collection = {
            OidConstant.SYS_OBJECT_ID: {"value": "Some object ID"},
            OidConstant.SYS_DESCR: {"value": "Linux Suse 1.2.3.4"},
        }

        descr = extract_desc(realtime_collection)
        self.assertEqual(2, len(descr))
        self.assertEqual("Linux Suse 1.2.3.4", descr[0])
        self.assertEqual("Some object ID", descr[1])

    def test_return_tuple_with_none_values(self):
        realtime_collection = {}

        descr = extract_desc(realtime_collection)
        self.assertEqual(2, len(descr))
        self.assertIsNone(descr[0])
        self.assertIsNone(descr[1])

    def test_assign_profile_to_device(self):
        profiles = {"zeus": {"patterns": [".*zeus.*"], "frequency": 20}}

        result = assign_profiles_to_device(profiles, ("My zeus device", None))

        self.assertEqual(len(result), 1)
        profile, frequency = next(iter(result))
        self.assertEqual("zeus", profile)
        self.assertEqual(frequency, 20)

    def test_assign_multiple_profile_to_device(self):
        profiles = {
            "zeus": {"patterns": [".*zeus.*"], "frequency": 20},
            "linux": {"patterns": [".*linux.*"], "frequency": 30},
        }

        result = assign_profiles_to_device(
            profiles, ("My zeus device, linux 2.3.4", None)
        )

        self.assertEqual(len(result), 2)
        profile, frequency = result[0]
        self.assertEqual("zeus", profile)
        self.assertEqual(frequency, 20)

        profile, frequency = result[1]
        self.assertEqual("linux", profile)
        self.assertEqual(frequency, 30)

    def test_assign_multiple_profile_to_device_from_different_descs(self):
        profiles = {
            "zeus": {"patterns": [".*zeus.*"], "frequency": 20},
            "linux": {"patterns": [".*linux.*"], "frequency": 30},
        }

        result = assign_profiles_to_device(profiles, ("My zeus device", "linux 2.3.4"))

        self.assertEqual(len(result), 2)
        profile, frequency = result[0]
        self.assertEqual("zeus", profile)
        self.assertEqual(frequency, 20)

        profile, frequency = result[1]
        self.assertEqual("linux", profile)
        self.assertEqual(frequency, 30)

    def test_no_assignment_when_patterns_are_missing(self):
        profiles = {"zeus": {"frequency": 20}}

        result = assign_profiles_to_device(profiles, ("My zeus device", None))

        self.assertEqual(len(result), 0)
