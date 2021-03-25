from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

from splunk_connect_for_snmp_poller.manager.mib_server_client import get_translation
from pysnmp.hlapi import *
import json
import os

from pysnmp.smi import builder, view, compiler, rfc1902
from pysmi import debug as pysmi_debug

pysmi_debug.setLogger(pysmi_debug.Debug("compiler"))


def is_metric_data(hec_config, varBinds):
    """
    Check the condition to see if the varBinds belongs to metric data.
     - if mib value is int/float
    @param hec_config: HecConfiguration Object
    @param varBinds: varBinds Object
    @return: boolean
    """
    # check if the mib value is float
    for name, value in varBinds:
        try:
            float(value.prettyPrint())
            return True
        except ValueError:
            return False


def get_translated_string(mib_server_url, hec_config, varBinds):
    """
    Get the translated/formatted var_binds string depending on whether the varBinds is an event or metric
    Note: if it failed to get translation, return the the original varBinds
    @return result: formated string ready to be sent to Splunk HEC
    @return metric: boolean, metric data flag
    """
    logger.info(f"I got these var binds: {varBinds}")
    # check if this is metric data
    metric = is_metric_data(hec_config, varBinds)
    # Get Original varbinds as backup in case the mib-server is unreachable
    try:
        for name, val in varBinds:
            # Original oid
            # TODO Discuss: should we return the original oid
            # if the mib server is unreachable
            # should we format it align with the format of the translated one
            # result = "{} = {}".format(name.prettyPrint(), val.prettyPrint())
            if metric:
                result = {
                    "metric_name": name.prettyPrint(),
                    "_value": val.prettyPrint(),
                }
                result = json.dumps(result)
            else:
                result = '{oid}="{value}"'.format(
                    oid=name.prettyPrint(), value=val.prettyPrint()
                )

    except Exception as e:
        logger.info(
            f"Exception occurred while logging varBinds name & value. Exception: {e}"
        )

    # Overrid the varBinds string with translated varBinds string
    try:
        result = get_translation(varBinds, mib_server_url, metric)
        logger.info(f"=========result=======\n{result}")
    except Exception as e:
        logger.info(f"Could not perform translation. Exception: {e}")
    logger.info(
        f"###############final result -- metric: {metric}#######################\n{result}"
    )
    return result, metric


def mib_string_handler(
    snmp_engine,
    host,
    port,
    version,
    community,
    mib_file,
    mib_name,
    mib_index,
    mib_server_url,
    hec_config,
    server_config,
    results,
):
    """
    Perform the SNMP Get for mib-name/string,
    e.g. ['SNMPv2-MIB', 'sysUpTime',0] (syntax -> [<mib_file_name>, <mib_name/string>, <min_index>])
    which querise the info correalted to this specific mib-name/string (e.g. sysUpTime)
    """
    logger.info(
        f"Executing get_by_mib_name() with {host} {port} {version} {community} {mib_file} {mib_name} {mib_index} {mib_server_url}"
    )
    mibBuilder = builder.MibBuilder()
    mibViewController = view.MibViewController(mibBuilder)
    config = {"sources": [os.environ["MIBS_FILES_URL"]]}
    compiler.addMibCompiler(mibBuilder, **config)

    try:
        errorIndication, errorStatus, errorIndex, varBinds = next(
            getCmd(
                snmp_engine,
                CommunityData(community, mpModel=0),
                UdpTransportTarget((host, port)),
                ContextData(),
                ObjectType(
                    ObjectIdentity(mib_file, mib_name, mib_index)
                ).resolveWithMib(mibViewController),
            )
        )

        if errorIndication:
            result = f"error: {errorIndication}"
            logger.info(result)
            results.append((result, False))
        elif errorStatus:
            result = "error: %s at %s" % (
                errorStatus.prettyPrint(),
                errorIndex and varBinds[int(errorIndex) - 1][0] or "?",
            )
            logger.info(result)
            results.append((result, False))
        else:
            logger.info(f"varBinds: {varBinds}")
            for varBind in varBinds:
                logger.info(" = ".join([x.prettyPrint() for x in varBind]))
            result, metric = get_translated_string(mib_server_url, hec_config, varBinds)
            results.append((result, metric))
    except Exception as e:
        logger.error(f"Error happened while polling by mib name: {e}")


def get_handler(
    snmp_engine, community, host, port, profile, mib_server_url, hec_config, results
):
    """
    Perform the SNMP Get for an oid,
    e.g. 1.3.6.1.2.1.1.9.1.2.1,
    which queries the info correalted to this specific oid
    """
    errorIndication, errorStatus, errorIndex, varBinds = next(
        getCmd(
            snmp_engine,
            CommunityData(community, mpModel=0),
            UdpTransportTarget((host, port)),
            ContextData(),
            ObjectType(ObjectIdentity(profile)),
        )
    )
    if errorIndication:
        result = f"error: {errorIndication}"
        metric = False
        logger.error(result)
    elif errorStatus:
        result = "error: %s at %s" % (
            errorStatus.prettyPrint(),
            errorIndex and varBinds[int(errorIndex) - 1][0] or "?",
        )
        metric = False
        logger.error(result)
    else:
        result, metric = get_translated_string(mib_server_url, hec_config, varBinds)
    results.append((result, metric))


def walk_handler(
    snmp_engine, community, host, port, profile, mib_server_url, hec_config, results
):
    """
    Perform the SNMP Walk for oid end with *,
    e.g. 1.3.6.1.2.1.1.9.*,
    which queries the infos correalted to all the oids that underneath the prefix before the *, e.g. 1.3.6.1.2.1.1.9
    """
    for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
        snmp_engine,
        CommunityData(community),
        UdpTransportTarget((host, port)),
        ContextData(),
        ObjectType(ObjectIdentity(profile[:-2])),
        lexicographicMode=False,
    ):

        if errorIndication:
            result = f"error: {errorIndication}"
            logger.info(result)
            results.append((result, False))
            break
        elif errorStatus:
            result = "error: %s at %s" % (
                errorStatus.prettyPrint(),
                errorIndex and varBinds[int(errorIndex) - 1][0] or "?",
            )
            logger.info(result)
            results.append((result, False))
            break
        else:
            result, metric = get_translated_string(mib_server_url, hec_config, varBinds)
            results.append((result, metric))


def parse_port(host):
    """
    @params host: host filed in inventory.csv. e.g 10.202.12.56, 127.0.0.1:1162
    @return host, port
    """
    if ":" in host:
        tmp = host.split(":")
        host = tmp[0]
        port = tmp[1]
    else:
        port = 161
    return host, port
