import logging

import pytest

from splunk_connect_for_snmp_poller.mongo import WalkedHostsRepository

logger = logging.getLogger(__name__)


def is_mongo_running(mongo_config):
    client = WalkedHostsRepository(mongo_config)
    return client.is_connected()


@pytest.fixture(scope='session')
def mongo_service(request, docker_services):
    service_name = 'mongo'
    docker_services.start(service_name)
    port = docker_services.port_for(service_name, 27017)
    configuration = {'host': 'localhost', 'port': port, 'database': 'snmp_poller', 'collection': 'walked_hosts'}

    docker_services.wait_until_responsive(timeout=180.0, pause=1.0, check=lambda: is_mongo_running(configuration))
    logger.info(f'Initialized {service_name} from Docker with {configuration}')
