import logging
import os

import pytest

logger = logging.getLogger(__name__)


@pytest.fixture(scope='session')
def splunk_external_configuration(request):
    logger.info('Calling splunk_external_configuration()')
    configuration = {'host': request.config.getoption('splunk_host'), 'port': request.config.getoption('splunk_port'),
                     'username': request.config.getoption('splunk_user'),
                     'password': request.config.getoption('splunk_password'),
                     'connect_max_retries': request.config.getoption('splunk_connect_max_retries')}
    return configuration


@pytest.fixture(scope='session')
def splunk_service(request):
    logger.info('Calling splunk_configuration()')
    request_type = request.config.getoption('splunk_type')
    if request_type == 'external':
        request.fixturenames.append('splunk_external_configuration')
        configuration = request.getfixturevalue('splunk_external_configuration')
    elif request_type == 'docker':
        os.environ['SPLUNK_PASSWORD'] = request.config.getoption('splunk_password')
        request.fixturenames.append('splunk_docker_configuration')
        configuration = request.getfixturevalue('splunk_docker_configuration')

    return configuration
