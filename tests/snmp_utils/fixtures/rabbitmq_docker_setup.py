import logging
from time import sleep

import pytest

logger = logging.getLogger(__name__)


def is_rabbitmq_running(mongo_config):
    sleep(5)
    return True


@pytest.fixture(scope='session')
def rabbitmq_service(request, docker_services):
    service_name = 'rabbitmq'
    docker_services.start(service_name)
    port = docker_services.port_for(service_name, 5672)
    configuration = {}

    docker_services.wait_until_responsive(timeout=180.0, pause=1.0, check=lambda: is_rabbitmq_running(configuration))
    logger.info(f'Initialized {service_name} from Docker with {configuration}')
