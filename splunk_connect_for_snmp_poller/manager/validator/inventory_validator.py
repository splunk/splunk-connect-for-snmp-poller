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
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import logging
import re

logger = logging.getLogger(__name__)

profile_pattern = re.compile("^[A-Za-z0-9_-]*$")

SNMP_VERSION_1 = "1"
SNMP_VERSION_2C = "2c"
SNMP_VERSION_3 = "3"
snmp_allowed_versions = {SNMP_VERSION_1, SNMP_VERSION_2C, SNMP_VERSION_3}


def should_process_inventory_line(host_from_inventory):
    stripped = host_from_inventory.lstrip()
    return stripped and stripped[:1] != "#"


def is_valid_number(port, validation):
    try:
        integer_value = int(port)
        return validation(integer_value)
    except ValueError:
        logger.error(f"{port} is not a number")
        return False


def is_valid_port(port):
    def up_to_65535(p):
        return 1 <= p <= 65535

    valid_port = is_valid_number(port, up_to_65535)
    if not valid_port:
        logger.error(f"Port {port} is out of range 1 <= {port} <= 65535")
    return valid_port


def is_valid_second_quantity(seconds):
    def any_positive_number(positive_number):
        return positive_number > 0

    valid_port = is_valid_number(seconds, any_positive_number)
    if not valid_port:
        logger.error(f"Negative number of seconds: {seconds}")
    return valid_port


def resolve_host(hostname):
    import socket

    try:
        socket.gethostbyname(hostname)
        return bool(hostname)
    except OSError:
        logger.error(f"Cannot resolve {hostname}")
        return False


def is_valid_host(host):
    host_port = [elem.strip() for elem in host.split(":")]
    length = len(host_port)
    if length == 1:
        return resolve_host(host_port[0])
    elif length == 2:
        return resolve_host(host_port[0]) and is_valid_port(host_port[1])
    return False


def is_valid_version(version):
    global snmp_allowed_versions
    valid_version = version in snmp_allowed_versions
    if not valid_version:
        logger.error(
            f"{version} is an invalid version. Only {snmp_allowed_versions} are allowed"
        )
    return valid_version


def is_valid_community(community_string):
    return True if community_string.strip() else False


def is_valid_profile(profile):
    return profile_pattern.match(profile.strip())


def is_valid_inventory_line_from_dict(host, version, community, profile, seconds):
    if None in [host, version, community, profile]:
        return False

    valid_inventory_line = (
        is_valid_host(host.strip())
        and is_valid_version(version.strip())
        and is_valid_community(community.strip())
        and is_valid_profile(profile.strip())
        and (seconds is None or is_valid_second_quantity(seconds))
    )
    if not valid_inventory_line:
        logger.error(
            f"Invalid inventory line [{host}], version = [{version}], community = [{community}], profile = [{profile}],"
            f" seconds = [{seconds}]"
        )
    return valid_inventory_line
