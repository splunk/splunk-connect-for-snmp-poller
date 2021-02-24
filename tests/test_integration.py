import logging

logger = logging.getLogger(__name__)


def test_splunk_integration(splunk_service):
    logger.info('Running test_splunk_integration()')
    assert True
