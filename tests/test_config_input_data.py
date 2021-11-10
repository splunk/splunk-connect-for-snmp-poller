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

parsed_config_root_with_error = {
    "enricher_with_error": {
        "oidFamily": {
            "IF-MIB": {
                "existingVarBinds": [
                    {"ifIndex": "interface_index"},
                    {"ifDescr": "interface_desc"},
                ]
            }
        }
    }
}

parsed_config_family_with_error = {
    "enricher": {
        "oidFamily_with_error": {
            "IF-MIB": {
                "existingVarBinds": [
                    {"ifIndex": "interface_index"},
                    {"ifDescr": "interface_desc"},
                ]
            }
        }
    }
}

parsed_config_if_mib_with_error = {
    "enricher": {
        "oidFamily": {
            "IF-MIB_with_error": {
                "existingVarBinds": [
                    {"ifIndex": "interface_index"},
                    {"ifDescr": "interface_desc"},
                ]
            }
        }
    }
}

parsed_config_if_mib_without_elements = {"enricher": {"oidFamily": {"IF-MIB": {"existingVarBinds": []}}}}  # type: ignore # noqa: E501

parsed_config_correct = {
    "enricher": {
        "oidFamily": {
            "IF-MIB": {
                "existingVarBinds": [
                    {"id": "ifIndex", "name": "interface_index", "ttl": 10},
                    {"id": "ifDescr", "name": "interface_desc", "ttl": 20},
                ]
            }
        }
    }
}

parsed_config_correct_three_fields = {
    "enricher": {
        "oidFamily": {
            "IF-MIB": {
                "existingVarBinds": [
                    {"id": "ifIndex", "name": "interface_index", "ttl": 10},
                    {"id": "ifDescr", "name": "interface_desc", "ttl": 20},
                    {"id": "ifInUcastPkts", "name": "total_in_packets", "ttl": 30},
                ]
            }
        }
    }
}

parsed_config_correct_one_non_existing_field = {
    "enricher": {
        "oidFamily": {
            "IF-MIB": {
                "existingVarBinds": [
                    {"id": "ifIndex", "name": "interface_index", "ttl": 10},
                    {"id": "ifDescr", "name": "interface_desc", "ttl": 20},
                    {"id": "ifUknownField", "name": "unknown_field", "ttl": 5},
                ]
            }
        }
    }
}

parsed_config_duplicate_keys = {
    "enricher": {
        "oidFamily": {
            "IF-MIB": {
                "existingVarBinds": [
                    {"id": "ifIndex", "name": "interface_index", "ttl": 10},
                    {"id": "ifIndex", "name": "interface_index", "ttl": 10},
                    {"id": "ifIndex", "name": "interface_index2", "ttl": 10},
                ]
            }
        }
    }
}

parsed_config_with_additional_varbinds_ifmib = {
    "enricher": {
        "oidFamily": {
            "IF-MIB": {
                "existingVarBinds": [
                    {"id": "ifIndex", "name": "interface_index", "ttl": 10},
                    {"id": "ifDescr", "name": "interface_desc", "ttl": 20},
                    {"id": "ifInUcastPkts", "name": "total_in_packets", "ttl": 5},
                ],
                "additionalVarBinds": [
                    {"indexNum": "index_num"},
                ],
            }
        }
    }
}

parsed_config_with_additional_varbinds_snmp_mib = {
    "enricher": {
        "oidFamily": {
            "IF-MIB": {
                "additionalVarBinds": [
                    {"indexNum": "index_num"},
                ],
            },
            "SNMPv2-MIB": {
                "additionalVarBinds": [
                    {"indexNum": "index_number"},
                ],
            },
        }
    }
}
