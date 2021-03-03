import logging
import json
import requests
import os


logger = logging.getLogger(__name__)

def get_translation(var_binds, mib_server_url):
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
            # "oid": name.prettyPrint(),
            "oid": str(name),
            "oid_type": name.__class__.__name__,
            # "val": val.prettyPrint(),
            "val": str(val),
            "val_type": val.__class__.__name__
        }
        var_binds_list.append(var_bind)
    payload["var_binds"] = var_binds_list
    payload = json.dumps(payload)

    # Send the POST request to mib server
    headers = {'Content-type': 'application/json'}
    endpoint = "translation"
    TRANSLATION_URL = os.path.join(mib_server_url.strip('/'), endpoint)
    logger.debug(f"[-] TRANSLATION_URL: {TRANSLATION_URL}")
    try:
        resp = requests.request("POST", TRANSLATION_URL, headers=headers, data=payload)
    except Exception as e:
        logger.error(f"MIB server is unreachable! Error happened while communicating to MIB server to perform the Translation: {e}")
    if resp.status_code != 200:
        logger.error(f"[-] Mib Server API Error with code: {resp.status_code}")
    trap_event_string = resp.text
    return trap_event_string