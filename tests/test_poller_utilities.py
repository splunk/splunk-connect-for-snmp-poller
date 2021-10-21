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
    deleted_oid_families,
    get_frequency,
    is_ifmib_different,
    return_database_id,
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
        profiles = {"profiles": {"some_profile": {"frequency": 20}}}
        result = get_frequency(agent, profiles, 60)
        self.assertEqual(result, 20)

    def test_return_default_frequency_when_agent_profile_not_present_in_profiles(self):
        agent = {"profile": "some_profile"}
        profiles = {"profiles": {"some_profile_2": {"frequency": 20}}}
        result = get_frequency(agent, profiles, 60)
        self.assertEqual(result, 60)

    def test_return_default_frequency_when_profiles_are_empty(self):
        agent = {"profile": "some_profile"}
        profiles = {}
        result = get_frequency(agent, profiles, 60)
        self.assertEqual(result, 60)

    def test_return_default_frequency_when_profile_matched_is_dynamic(self):
        agent = {"profile": "*"}
        profiles = {"profiles": {"some_profile": {"frequency": 20}}}
        result = get_frequency(agent, profiles, 60)
        self.assertEqual(result, 60)

    def test_return_default_frequency_when_frequency_is_missing(self):
        agent = {"profile": "some_profile"}
        profiles = {"profiles": {"some_profile_2": {}}}
        result = get_frequency(agent, profiles, 60)
        self.assertEqual(result, 60)

    def test_return_default_frequency_when_there_is_no_profiles(self):
        agent = {"profile": "some_profile"}
        profiles = {"profiles": {}}
        result = get_frequency(agent, profiles, 60)
        self.assertEqual(result, 60)

    def test_compare_enrichers_different_additional(self):
        new_enricher = {
            "oidFamily": {
                "IF-MIB": {
                    "existingVarBinds": [
                        {"ifIndex": "interface_index"},
                        {"ifDescr": "interface_desc"},
                        {"ifPhysAddress": "MAC_address"},
                    ],
                    "additionalVarBinds": [{"indexNum": "index_number"}],
                },
                "SNMPv2-MIB": {
                    "additionalVarBinds": [{"indexNum": "index_number_snmp_2"}]
                },
                "TCP-MIB": {
                    "additionalVarBinds": [{"indexNum": "index_number_tcp_33"}]
                },
            }
        }
        old_enricher = {
            "oidFamily": {
                "IF-MIB": {
                    "existingVarBinds": [
                        {"ifIndex": "interface_index"},
                        {"ifDescr": "interface_desc"},
                        {"ifPhysAddress": "MAC_address"},
                    ],
                    "additionalVarBinds": [{"indexNum": "index_number"}],
                },
                "TCP-MIB": {
                    "additionalVarBinds": [{"indexNum": "index_number_tcp_33"}]
                },
            }
        }
        result = is_ifmib_different(old_enricher, new_enricher)
        self.assertFalse(result)

    def test_compare_enrichers_different_ifmib(self):
        new_enricher = {
            "oidFamily": {
                "IF-MIB": {
                    "existingVarBinds": [
                        {"ifIndex": "interface_index"},
                        {"ifDescr": "interface_desc"},
                        {"ifPhysAddress": "MAC_address"},
                    ],
                    "additionalVarBinds": [{"indexNum": "index_number"}],
                },
                "SNMPv2-MIB": {
                    "additionalVarBinds": [{"indexNum": "index_number_snmp_2"}]
                },
                "TCP-MIB": {
                    "additionalVarBinds": [{"indexNum": "index_number_tcp_33"}]
                },
            }
        }
        old_enricher = {
            "oidFamily": {
                "IF-MIB": {
                    "existingVarBinds": [
                        {"ifIndex": "interface_index"},
                        {"ifPhysAddress": "MAC_address"},
                    ],
                    "additionalVarBinds": [{"indexNum": "index_number"}],
                },
                "TCP-MIB": {
                    "additionalVarBinds": [{"indexNum": "index_number_tcp_33"}]
                },
            }
        }
        result = is_ifmib_different(old_enricher, new_enricher)
        self.assertTrue(result)

    def test_compare_enrichers_different_without_additional(self):
        new_enricher = {
            "oidFamily": {
                "IF-MIB": {
                    "existingVarBinds": [
                        {"ifIndex": "interface_index"},
                        {"ifDescr": "interface_desc"},
                        {"ifPhysAddress": "MAC_address"},
                    ],
                    "additionalVarBinds": [{"indexNum": "index_number"}],
                }
            }
        }
        old_enricher = {
            "oidFamily": {
                "IF-MIB": {
                    "existingVarBinds": [
                        {"ifIndex": "interface_index"},
                        {"ifPhysAddress": "MAC_address"},
                    ],
                    "additionalVarBinds": [{"indexNum": "index_number"}],
                }
            }
        }
        result = is_ifmib_different(old_enricher, new_enricher)
        self.assertTrue(result)

    def test_compare_enrichers_empty(self):
        new_enricher = {}
        old_enricher = {}
        result = is_ifmib_different(old_enricher, new_enricher)
        self.assertFalse(result)

    def test_compare_enrichers_one_empty(self):
        new_enricher = {}
        old_enricher = {
            "oidFamily": {
                "IF-MIB": {
                    "existingVarBinds": [
                        {"ifIndex": "interface_index"},
                        {"ifDescr": "interface_desc"},
                        {"ifPhysAddress": "MAC_address"},
                    ],
                    "additionalVarBinds": [{"indexNum": "index_number"}],
                }
            }
        }
        result = is_ifmib_different(old_enricher, new_enricher)
        self.assertTrue(result)

    def test_deleted_oid_families(self):
        old_enricher = {
            "oidFamily": {
                "IF-MIB": {
                    "existingVarBinds": [
                        {"ifIndex": "interface_index"},
                        {"ifDescr": "interface_desc"},
                        {"ifPhysAddress": "MAC_address"},
                    ],
                    "additionalVarBinds": [{"indexNum": "index_number"}],
                },
                "SNMPv2-MIB": {
                    "additionalVarBinds": [{"indexNum": "index_number_snmp_2"}]
                },
                "TCP-MIB": {
                    "additionalVarBinds": [{"indexNum": "index_number_tcp_33"}]
                },
            }
        }
        new_enricher = {
            "oidFamily": {
                "IF-MIB": {
                    "existingVarBinds": [
                        {"ifIndex": "interface_index"},
                        {"ifPhysAddress": "MAC_address"},
                    ],
                    "additionalVarBinds": [{"indexNum": "index_number"}],
                }
            }
        }
        result = deleted_oid_families(old_enricher, new_enricher)
        self.assertEqual(result, {"SNMPv2-MIB", "TCP-MIB"})

    def test_deleted_oid_families_no_change(self):
        new_enricher = {
            "oidFamily": {
                "IF-MIB": {
                    "existingVarBinds": [
                        {"ifIndex": "interface_index"},
                        {"ifDescr": "interface_desc"},
                        {"ifPhysAddress": "MAC_address"},
                    ],
                    "additionalVarBinds": [{"indexNum": "index_number"}],
                },
                "SNMPv2-MIB": {
                    "additionalVarBinds": [{"indexNum": "index_number_snmp_2"}]
                },
                "TCP-MIB": {
                    "additionalVarBinds": [{"indexNum": "index_number_tcp_33"}]
                },
            }
        }
        old_enricher = {
            "oidFamily": {
                "IF-MIB": {
                    "existingVarBinds": [
                        {"ifIndex": "interface_index"},
                        {"ifPhysAddress": "MAC_address"},
                    ],
                    "additionalVarBinds": [{"indexNum": "index_number"}],
                }
            }
        }
        result = deleted_oid_families(old_enricher, new_enricher)
        self.assertEqual(result, set())

    def test_deleted_oid_families_with_ifmib(self):
        new_enricher = {
            "oidFamily": {
                "SNMPv2-MIB": {
                    "additionalVarBinds": [{"indexNum": "index_number_snmp_2"}]
                },
                "TCP-MIB": {
                    "additionalVarBinds": [{"indexNum": "index_number_tcp_33"}]
                },
            }
        }
        old_enricher = {
            "oidFamily": {
                "IF-MIB": {
                    "existingVarBinds": [
                        {"ifIndex": "interface_index"},
                        {"ifDescr": "interface_desc"},
                        {"ifPhysAddress": "MAC_address"},
                    ],
                    "additionalVarBinds": [{"indexNum": "index_number"}],
                },
                "SNMPv2-MIB": {
                    "additionalVarBinds": [{"indexNum": "index_number_snmp_2"}]
                },
                "TCP-MIB": {
                    "additionalVarBinds": [{"indexNum": "index_number_tcp_33"}]
                },
            }
        }
        result = deleted_oid_families(old_enricher, new_enricher)
        self.assertEqual(result, set())
