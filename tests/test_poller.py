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
import sys
from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch

sys.modules["splunk_connect_for_snmp_poller.manager.celery_client"] = Mock()
from splunk_connect_for_snmp_poller.manager.poller import Poller  # noqa: E402


class TestPollerUtilities(TestCase):
    def test_run_enricher_changed_check_when_enricher_is_deleted(self):
        server_config = {"mongo": ""}
        with patch(
            "splunk_connect_for_snmp_poller.mongo.WalkedHostsRepository.__init__"
        ) as mock:
            mock.return_value = None
            obj = Poller([], server_config)
            obj._old_enricher = {
                "IF-MIB": {
                    "existingVarBinds": [
                        {"ifIndex": "interface_index"},
                        {"ifDescr": "interface_desc"},
                        {"ifPhysAddress": "MAC_address"},
                    ],
                    "additionalVarBinds": [{"indexNum": "index_number"}],
                }
            }
            with patch(
                "splunk_connect_for_snmp_poller.mongo.WalkedHostsRepository.delete_all_static_data"
            ):
                obj.run_enricher_changed_check({}, {"127.0.0.1:161": MagicMock()})
            self.assertEqual(obj._old_enricher, {})
