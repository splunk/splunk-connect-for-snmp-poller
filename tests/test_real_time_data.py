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
