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
import json
import logging
import os
import requests

import aiohttp
import backoff as backoff
from aiohttp import ClientSession

from splunk_connect_for_snmp_poller.utilities import format_value_for_mib_server

logger = logging.getLogger(__name__)


class SharedException(Exception):
    """Raised when the input value is too large"""

    def __init__(self, msg="Default Shared Exception occurred.", *args):
        super().__init__(msg, *args)


async def get_translation(var_binds, mib_server_url, data_format):
    """
    @param var_binds: var_binds object getting from SNMP agents
    @param mib_server_url: URL of SNMP MIB server
    @param data_format: format of data
    @return: translated string
    """
    # Construct the payload
    payload = {}
    var_binds_list = []
    # *TODO*: Below differs a bit between poller and trap!

    for name, val in var_binds:
        var_bind = {
            "oid": str(name),
            "oid_type": name.__class__.__name__,
            "val": format_value_for_mib_server(val, val.__class__.__name__),
            "val_type": val.__class__.__name__,
        }
        var_binds_list.append(var_bind)
    payload["var_binds"] = var_binds_list
    payload = json.dumps(payload)

    # Send the POST request to mib server
    headers = {"Content-type": "application/json"}
    endpoint = "translation"
    translation_url = os.path.join(mib_server_url.strip("/"), endpoint)
    logger.debug(f"[-] translation_url: {translation_url}")

    try:
        return await get_url(translation_url, headers, payload, data_format)
    except Exception as e:
        logger.error(f"Error getting translation from MIB Server: {e}")
        raise SharedException(f"Error getting translation from MIB Server: {e}")


@backoff.on_exception(backoff.expo, aiohttp.ClientError, max_tries=3)
async def get_url(url, headers, payload, data_format):
    async with ClientSession(raise_for_status=True) as session:
        resp = await session.post(
            url,
            headers=headers,
            data=payload,
            params={"data_format": data_format},
            timeout=1,
        )
        return await resp.text()


def get_mib_profiles():
    mib_server_url = os.environ["MIBS_SERVER_URL"]
    endpoint = "profiles"
    profiles_url = os.path.join(mib_server_url.strip("/"), endpoint)

    try:
        return requests.get(profiles_url).text
    except Exception:
        return {}

