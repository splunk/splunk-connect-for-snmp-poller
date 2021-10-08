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
from unittest.mock import Mock

sys.modules["splunk_connect_for_snmp_poller.manager.celery_client"] = Mock()
from splunk_connect_for_snmp_poller.manager.poller_utilities import (  # noqa: E402
    create_poller_scheduler_entry_key,
    return_database_id, get_frequency,
)


class TestPollerUtilities(TestCase):
    def test_return_database_id_bare_ip(self):
        host = "127.0.0.1"
        self.assertEqual(return_database_id(host), "127.0.0.1:161")

    def test_return_database_id_ip_with_port(self):
        host = "127.0.0.1:29"
        self.assertEqual(return_database_id(host), "127.0.0.1:29")

    def test_return_database_id_entry(self):
        host = "127.0.0.1#1.3.6.1.2.1.2.*"
        self.assertEqual(return_database_id(host), "127.0.0.1:161")

    def test_return_database_id_entry_with_port(self):
        host = "127.0.0.1:162#1.3.6.1.2.1.2.*"
        self.assertEqual(return_database_id(host), "127.0.0.1:162")

    def test_create_poller_scheduler_entry_key(self):
        self.assertEqual(
            create_poller_scheduler_entry_key("127.0.0.1", "1.3.6.1.2.1.2"),
            "127.0.0.1#1.3.6.1.2.1.2",
        )

    def test_return_frequency(self):
        agent = {"profile": "some_profile"}
        profiles = {"profiles": {"some_profile":
                        {"frequency": 20}
                    }}
        result = get_frequency(agent, profiles, 60)
        self.assertEqual(result, 20)

    def test_return_default_frequency_when_agent_does_not_have_profile(self):
        agent = {}
        profiles = {"profiles": {"some_profile":
                        {"frequency": 20}
                    }}
        result = get_frequency(agent, profiles, 60)
        self.assertEqual(result, 60)

    def test_return_default_frequency_when_agent_profile_not_present_in_profiles(self):
        agent = {"profile": "some_profile"}
        profiles = {"profiles": {"some_profile_2":
                        {"frequency": 20}
                    }}
        result = get_frequency(agent, profiles, 60)
        self.assertEqual(result, 60)

    def test_return_default_frequency_when_profiles_are_empty(self):
        agent = {"profile": "some_profile"}
        profiles = {}
        result = get_frequency(agent, profiles, 60)
        self.assertEqual(result, 60)

    def test_return_default_frequency_when_profile_matched_is_dynamic(self):
        agent = {"profile": "*"}
        profiles = {"profiles": {"some_profile":
                        {"frequency": 20}
                    }}
        result = get_frequency(agent, profiles, 60)
        self.assertEqual(result, 60)
