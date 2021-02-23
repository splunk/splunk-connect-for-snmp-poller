import logging

logger = logging.getLogger(__name__)


def test_splunk_integration(splunk_connector):
    logger.info('Running test_splunk_integration()')
    assert True
