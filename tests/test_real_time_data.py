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
from splunk_connect_for_snmp_poller.manager.realtime.real_time_data import (
    should_redo_walk,
)
from splunk_connect_for_snmp_poller.manager.realtime.oid_constant import OidConstant


class ShouldRedoWalkTest(TestCase):
    def test_invalid_collection(self):
        self.assertFalse(should_redo_walk(None, None))
        self.assertFalse(should_redo_walk(None, {}))
        self.assertFalse(should_redo_walk({}, None))

    def test_when_restart_did_not_happen(self):
        realtime_collection = {
            OidConstant.SYS_UP_TIME_INSTANCE: {"value": "123", "type": "TimeTicks"},
        }
        current_get_result = {
            OidConstant.SYS_UP_TIME_INSTANCE: {"value": "123", "type": "TimeTicks"},
        }
        self.assertFalse(should_redo_walk(realtime_collection, current_get_result))

    def test_when_restart_happened(self):
        realtime_collection = {
            OidConstant.SYS_UP_TIME_INSTANCE: {"value": "123", "type": "TimeTicks"},
        }
        current_get_result = {
            OidConstant.SYS_UP_TIME_INSTANCE: {"value": "100", "type": "TimeTicks"},
        }
        self.assertTrue(should_redo_walk(realtime_collection, current_get_result))
