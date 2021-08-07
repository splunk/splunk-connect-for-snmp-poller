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
from unittest.mock import patch, Mock
import sys
from pysnmp.hlapi import ObjectIdentity, ObjectType

sys.modules["splunk_connect_for_snmp_poller.manager.celery_client"] = Mock()
from splunk_connect_for_snmp_poller.manager.task_utilities import VarbindCollection
from splunk_connect_for_snmp_poller.manager.tasks import sort_varbinds


def cast_helper(varbind):
    if isinstance(varbind, list):
        return [ObjectType(ObjectIdentity(varbind[0], varbind[1]))]
    else:
        return [ObjectType(ObjectIdentity(varbind))]


class TestTasks(TestCase):
    def test_sort_varbinds_get(self):
        varbinds = "1.3.6.1.2.1.2.2"
        get_varbinds_result = VarbindCollection(bulk=[], get=cast_helper(varbinds))
        actual_result = sort_varbinds([varbinds])
        self.assertEqual(str(actual_result.get), str(get_varbinds_result.get))

    @patch("splunk_connect_for_snmp_poller.manager.tasks.app")
    def test_sort_varbinds_bulk(self, app):
        varbinds = ["CISCO-FC-MGMT-MIB", "cfcmPortLcStatsEntry"]
        bulk_varbinds_result = VarbindCollection(bulk=cast_helper(varbinds), get=[])
        with patch(
            "splunk_connect_for_snmp_poller.manager.tasks.mib_string_handler",
            return_value=bulk_varbinds_result,
        ):
            actual_result = sort_varbinds([varbinds])
        self.assertEqual(str(actual_result.bulk), str(bulk_varbinds_result.bulk))

    @patch("splunk_connect_for_snmp_poller.manager.tasks.app")
    def test_sort_varbinds_bulk_star(self, app):
        varbinds = ["1.3.6.1.2.1.2.*"]
        bulk_varbinds_result = VarbindCollection(
            bulk=cast_helper("1.3.6.1.2.1.2"), get=[]
        )
        actual_result = sort_varbinds(varbinds)
        self.assertEqual(str(actual_result.bulk), str(bulk_varbinds_result.bulk))

    @patch("splunk_connect_for_snmp_poller.manager.tasks.app")
    def test_sort_varbinds_bulk_get(self, app):
        varbinds = ["1.3.6.1.2.1.2.*", "1.3.6.1.2.1.2.1"]
        varbinds_bulk = cast_helper("1.3.6.1.2.1.2")
        varbinds_result = VarbindCollection(
            bulk=varbinds_bulk, get=cast_helper("1.3.6.1.2.1.2.1")
        )
        actual_result = sort_varbinds(varbinds)
        self.assertEqual(str(actual_result.bulk), str(varbinds_result.bulk))
        self.assertEqual(str(actual_result.get), str(varbinds_result.get))

    @patch("splunk_connect_for_snmp_poller.manager.tasks.app")
    def test_sort_varbinds_empty(self, app):
        varbinds = []
        varbinds_result = VarbindCollection(bulk=[], get=[])
        actual_result = sort_varbinds(varbinds)
        self.assertEqual(actual_result.__dict__, varbinds_result.__dict__)
