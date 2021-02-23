def pytest_addoption(parser):
    group = parser.getgroup('splunk-addon')
    group.addoption('--splunk_type', action='store', dest='splunk_type', default='external', help='Type of Splunk')
    group.addoption('--splunk_host', action='store', dest='splunk_host', default='127.0.0.1',
                    help='Address of the Splunk Server')
    group.addoption('--splunk_port', action='store', dest='splunk_port', default='8089', help='Splunk rest port')
    group.addoption('--splunk_user', action='store', dest='splunk_user', default='admin2', help='Splunk login user')
    group.addoption('--splunk_password', action='store', dest='splunk_password', default='Changed@11',
                    help='Splunk password')
    group.addoption('--connect_max_retries', action='store', dest='splunk_connect_max_retries', default='600',
                    help='Max number of tries when connecting to Splunk before giving up')
