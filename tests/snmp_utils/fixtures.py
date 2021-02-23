import logging

import pytest

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def splunk_external_configuration(request):
    logger.info('Calling splunk_external_configuration()')
    configuration = {'host': request.config.getoption('splunk_host'), 'port': request.config.getoption('splunk_port'),
                     'username': request.config.getoption('splunk_user'),
                     'password': request.config.getoption('splunk_password'),
                     'connect_max_retries': request.config.getoption('splunk_connect_max_retries')}
    return configuration


@pytest.fixture(scope="session")
def splunk_configuration(request):
    logger.info('Calling splunk_configuration()')
    request_type = request.config.getoption('splunk_type')
    if request_type == 'external':
        request.fixturenames.append('splunk_external_configuration')
        configuration = request.getfixturevalue('splunk_external_configuration')

    return configuration


@pytest.fixture(scope="session")
def splunk_connector(splunk_configuration):
    logger.info('Calling splunk_connector()')
    tried = 0
    connect_max_retries = splunk_configuration["connect_max_retries"]
    while True:
        try:
            kwargs = {"username": splunk_configuration["username"], "password": splunk_configuration["password"],
                      "host": splunk_configuration["host"],
                      "port": splunk_configuration["port"]}
            logger.info(f"Trying to connect to Splunk using {kwargs}")
            connection = None  # client.connect(**kwargs)
        except ConnectionRefusedError as ex:
            tried += 1
            if tried > connect_max_retries:
                logger.error(f'Cannot connect to Splunk: {ex}')
                raise
        finally:
            return connection
