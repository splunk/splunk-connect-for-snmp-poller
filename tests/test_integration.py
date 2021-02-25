import logging

logger = logging.getLogger(__name__)


def test_splunk_integration(splunk_service, snmp_simulator_service):
    logger.info('Running test_splunk_integration()')
    assert True
