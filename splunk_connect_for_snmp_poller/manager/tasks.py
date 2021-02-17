from splunk_connect_for_snmp_poller.manager.celery_client import app


@app.task
def snmp_get(host, version, community, profile):
    return f"Executing SNMP GET for {host} version={version}"
