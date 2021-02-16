from celery import Celery

# app = Celery('celery', broker='amqp://guest@localhost//')
app = Celery('hello', broker='amqp://guest@localhost//', backend='rpc://',
             include=['splunk_connect_for_snmp_poller.manager.tasks'])

if __name__ == '__main__':
    app.start()
