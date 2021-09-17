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
    logger.debug(f"[-] TRANSLATION_URL: {translation_url}")

    try:
        # use Session with Retry
        async with ClientSession() as session:
            resp = await session.post(
                translation_url,
                headers=headers,
                data=payload,
                params={"data_format": data_format},
                timeout=1)
    except Exception as e:
        logger.error(
            f"MIB server unreachable! Error happened while communicating to MIB server to perform the Translation: {e}"
        )
        raise SharedException("MIB server is unreachable!")

    if resp.status != 200:
        logger.error(f"[-] MIB Server API Error with code: {resp.status}")
        raise SharedException(f"MIB Server API Error with code: {resp.status}")

    # *TODO*: For future release could retain failed translations in some place to re-translate.

    return await resp.text()
