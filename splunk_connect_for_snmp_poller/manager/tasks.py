from splunk_connect_for_snmp_poller.manager.celery_client import app


@app.task
def add(x, y):
    return x + y