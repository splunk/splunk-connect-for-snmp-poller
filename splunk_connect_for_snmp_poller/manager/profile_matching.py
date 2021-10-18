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
import logging.config
import re

import yaml

from splunk_connect_for_snmp_poller.manager.mib_server_client import get_mib_profiles
from splunk_connect_for_snmp_poller.manager.realtime.oid_constant import OidConstant
from splunk_connect_for_snmp_poller.utilities import multi_key_lookup

logger = logging.getLogger(__name__)


def extract_desc(realtime_collection):
    sys_descr = multi_key_lookup(realtime_collection, (OidConstant.SYS_DESCR, "value"))
    sys_object_id = multi_key_lookup(
        realtime_collection, (OidConstant.SYS_OBJECT_ID, "value")
    )
    return sys_descr, sys_object_id


def assign_profiles_to_device(profiles, device_desc):
    result = []
    for profile in profiles:
        if "patterns" in profiles[profile]:
            match_profile_with_device(device_desc, profile, profiles, result)
    return result


def match_profile_with_device(device_desc, profile, profiles, result):
    for pattern in profiles[profile]["patterns"]:
        for desc in device_desc:
            if desc and re.compile(pattern).match(desc):
                result.append((profile, profiles[profile]["frequency"]))
                return


def get_profiles(server_config):
    profiles = get_mib_profiles()
    mib_profiles = profiles if not profiles else yaml.safe_load(profiles)

    result = {}
    merged_profiles = {}
    if "profiles" in mib_profiles:
        merged_profiles.update(mib_profiles["profiles"])
    merged_profiles.update(server_config["profiles"])

    result["profiles"] = merged_profiles
    return result
