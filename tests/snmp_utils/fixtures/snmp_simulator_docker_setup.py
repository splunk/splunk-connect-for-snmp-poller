import logging

import pytest

logger = logging.getLogger(__name__)


def is_snmp_simulator_running(snmp_config):
    import pysnmp.hlapi as snmp
    iterator = snmp.getCmd(snmp.SnmpEngine(), snmp.CommunityData('public'),
                           snmp.UdpTransportTarget((snmp_config['host'], snmp_config['port'])),
                           snmp.ContextData(),
                           snmp.ObjectType(snmp.ObjectIdentity('1.3.6.1.2.1.1.1.0')))
    error_indication, error_status, error_index, var_binds = next(iterator)
    return True if error_indication is None else False


@pytest.fixture(scope='session')
def snmp_simulator_service(request, docker_services):
    service_name = 'snmpsim'
    docker_services.start(service_name)
    snmp_config = {'host': 'localhost', 'port': 161}
    docker_services.wait_until_responsive(timeout=180.0, pause=1.0,
                                          check=lambda: is_snmp_simulator_running(snmp_config))
    logger.info(f'Initialized {service_name} from Docker with {snmp_config}')
