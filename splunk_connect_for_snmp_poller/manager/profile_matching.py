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

logger = logging.getLogger(__name__)


def assign_profiles_to_device(profiles, device_desc):
    result = []
    for profile in profiles:
        for pattern in profile['patterns']:
            if re.compile(pattern).match(device_desc):
                result.append(profile)
                continue
    return result


def get_profiles(server_config):
    mib_profiles = yaml.safe_load(get_mib_profiles())

    result = {}
    merged_profiles = {}

    merged_profiles.update(mib_profiles['profiles'])
    merged_profiles.update(server_config['profiles'])

    result['profiles'] = merged_profiles
    return result
