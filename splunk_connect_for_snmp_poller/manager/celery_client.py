from celery import Celery

# app = Celery('celery', broker='amqp://guest@localhost//')
app = Celery('splunk_connect_for_snmp_poller', broker='amqp://guest@localhost//', backend='rpc://',
             include=['splunk_connect_for_snmp_poller.manager.tasks'])

# @app.task
# def snmp_get(host, version, community, profile):
#    return f"Executing SNMP GET for {host} version={version}"


if __name__ == '__main__':
    app.start()
