from celery import Celery
import os
import logging.config

logger = logging.getLogger(__name__)

logger.info(f"Start Celery Client")

app = Celery(__name__)

app.conf.update(
    {
        "broker_url": os.environ["CELERY_BROKER_URL"],
        "imports": ("splunk_connect_for_snmp_poller.manager.tasks",),
        "result_backend": "rpc://",
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
    }
)


if __name__ == "__main__":
    app.start()
