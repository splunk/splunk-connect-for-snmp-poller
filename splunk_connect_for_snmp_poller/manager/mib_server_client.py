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
import time

import requests as requests
from requests.adapters import HTTPAdapter
from urllib3 import Retry

logger = logging.getLogger(__name__)


def get_translation(var_binds, mib_server_url, data_format):
    """
    @param var_binds: var_binds object getting from SNMP agents
    @param mib_server_url: URL of SNMP MIB server
    @param data_format: format of data
    @return: translated string
    """
    payload = prepare_payload(var_binds)

    try:
        return get_url(mib_server_url, payload, data_format)
    except requests.Timeout:
        logger.exception("Time out occurred during call to MIB Server")
        raise
    except requests.ConnectionError:
        logger.exception("Can not connect to MIB Server for url - %s", mib_server_url)
        raise
    except Exception:
        logger.exception("Error getting translation from MIB Server")
        raise


def prepare_payload(var_binds):
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
    return payload


class SharedException(object):
    pass


def get_url(mib_server_url, payload, data_format):
    headers = {"Content-type": "application/json"}
    endpoint = "translation"
    translation_url = os.path.join(mib_server_url.strip("/"), endpoint)
    logger.debug("[-] translation_url: %s", translation_url)

    # Set up the request params
    params = {"data_format": data_format}

    try:
        # use Session with Retry
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        resp = session.post(
            translation_url, headers=headers, data=payload, params=params, timeout=60
        )

    except Exception as e:
        logger.error(
            f"MIB server unreachable! Error happened while communicating to MIB server to perform the Translation: {e}"
        )
        raise SharedException("MIB server is unreachable!")

    if resp.status_code != 200:
        logger.error(f"[-] MIB Server API Error with code: {resp.status_code}")
        raise SharedException(f"MIB Server API Error with code: {resp.status_code}")

    # *TODO*: For future release could retain failed translations in some place to re-translate.

    return resp.text



# 1.3.6.1.2.1.2.2.1.4.1|Integer|16436|16436|True
# 1.3.6.1.2.1.1.6.0|DisplayString|San Francisco, California, United States|San Francisco, California, United States|True
# 1.3.6.1.2.1.2.2.1.6.2|OctetString|<null>ybù@|0x00127962f940|False
# 1.3.6.1.2.1.1.9.1.2.7|ObjectIdentity|1.3.6.1.2.1.50|SNMPv2-SMI::mib-2.50|False
# 1.3.6.1.2.1.6.13.1.4.195.218.254.105.51684.194.67.10.226.22|IpAddress|ÂCâ|194.67.10.226|False
# 1.3.6.1.2.1.25.3.2.1.6.1025|Counter32|0|0|True
# 1.3.6.1.2.1.31.1.1.1.15.2|Gauge32|100|100|True
# 1.3.6.1.2.1.1.3.0|TimeTicks|148271768|148271768|True
# 1.3.6.1.4.1.2021.10.1.6.1|Opaque|x>ë|0x9f78043eeb851f|False
# 1.3.6.1.2.1.31.1.1.1.10.1|Counter64|453477588|453477588|True
#
# As you can see, for most types str(value) == value.prettyPrint(), however:
# - for Opaque, IpAddress, and OctetString we need to use prettyPrint(), otherwise the data is rubbish
# - any other type should use str() before sending data to MIB-server


def format_value_for_mib_server(value, value_type):
    if value_type in ("OctetString", "IpAddress", "Opaque"):
        return value.prettyPrint()
    else:
        return str(value)


def retry_getting_mib_profile(profiles_url: str):
    result, response = try_getting_mib_profile(profiles_url)
    while not result:
        time.sleep(10)
        result, response = try_getting_mib_profile(profiles_url)
    return response.text


def try_getting_mib_profile(profiles_url: str):
    logger.debug("Trying MIB connection")
    try:
        response = requests.get(profiles_url, timeout=3)
        return True, response
    except Exception:
        return False, None


def get_mib_profiles():
    mib_server_url = os.environ["MIBS_SERVER_URL"]
    endpoint = "profiles"
    profiles_url = os.path.join(mib_server_url.strip("/"), endpoint)

    return retry_getting_mib_profile(profiles_url)
