#
# Copyright 2021 Splunk Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import logging.config
import os

from celery import Celery

logger = logging.getLogger(__name__)

logger.info("Start Celery Client")

app = Celery(__name__)

app.conf.update(
    {
        "broker_url": '"' + os.environ["CELERY_BROKER_URL"] + '"',
        "imports": ("splunk_connect_for_snmp_poller.manager.tasks",),
        "result_backend": "rpc://",
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        "result_expires": 1,
        "task_ignore_result": True,
    }
)


if __name__ == "__main__":
    app.start()
