import logging
logger = logging.getLogger(__name__)

from splunk_connect_for_snmp_poller.manager.celery_client import app
from splunk_connect_for_snmp_poller.manager.mib_server_client import get_translation
from pysnmp.hlapi import *


@app.task
def snmp_get(host, version, community, profile, mib_server_url):
    
    # getCmd - snmpget
    logger.debug(f'Executing SNMP GET for {host} version={version}')
    
    # check if it's in mongo
    errorIndication, errorStatus, errorIndex, varBinds = next(
    getCmd(SnmpEngine(),
        CommunityData(community, mpModel=0),
        UdpTransportTarget((host, 1161)),
        ContextData(),
        #    ObjectType(ObjectIdentity('SNMPv2-MIB', 'sysDescr', 0)),
        #    ObjectType(ObjectIdentity('SNMPv2-MIB', 'sysUpTime', 0)),
        #    ObjectType(ObjectIdentity('1.3.6.1.2.1.1.2.0')),
        ObjectType(ObjectIdentity(profile)))
    )
    if errorIndication:
        logger.error(errorIndication)
    elif errorStatus:
        logger.error('%s at %s' % (errorStatus.prettyPrint(),
                            errorIndex and varBinds[int(errorIndex) - 1][0] or '?'))
    else:
        logger.debug(f"varBinds: {varBinds}")
        for varBind in varBinds:
            logger.debug(' = '.join([x.prettyPrint() for x in varBind]))
        for name, val in varBinds:
            logger.debug(str(name), str(val))
        
        result = get_translation(varBinds, mib_server_url)
        logger.debug("===\n\n{}\n\n===".format(result))
    # add in mongo
    
    return f'Executing SNMP GET for {host} version={version}'
