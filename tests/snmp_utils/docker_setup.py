import logging
import os
from ssl import SSLEOFError

import pytest
import splunklib.client as client

logger = logging.getLogger(__name__)


def is_responsive_splunk(splunk_conn_config):
    logger.info(f'Calling with parameters {splunk_conn_config}')
    try:
        connection_params = {'username': splunk_conn_config['username'], 'password': splunk_conn_config['password'],
                             'host': splunk_conn_config['host'], 'port': splunk_conn_config['port']}
        client.connect(**connection_params)
        logger.info(f'Connected to Splunk!')
        return True
    except ConnectionRefusedError:
        return False
    except SSLEOFError:
        return False


@pytest.fixture(scope='session')
def docker_compose_files(pytestconfig):
    # This took me hours to figure. We must return a collection!
    return [os.path.join(str(pytestconfig.rootdir), 'docker-compose.yml')]


@pytest.fixture(scope='session')
def splunk_docker_configuration(request, docker_services):
    logger.info('Calling splunk_docker_configuration()')

    service_name = 'splunk'
    docker_services.start(service_name)
    default_port = request.config.getoption('splunk_port')
    port = docker_services.port_for(service_name, int(default_port))

    configuration = {'host': docker_services.docker_ip, 'port': port,
                     'username': request.config.getoption('splunk_user'),
                     'password': request.config.getoption('splunk_password'),
                     'connect_max_retries': request.config.getoption('splunk_connect_max_retries')}

    logger.info(configuration)
    docker_services.wait_until_responsive(timeout=180.0, pause=1.0, check=lambda: is_responsive_splunk(configuration))
    logger.info('Initialized Splunk from Docker')

    return configuration
