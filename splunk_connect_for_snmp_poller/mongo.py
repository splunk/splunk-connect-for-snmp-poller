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
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import os


class WalkedHostsRepository:
    def __init__(self, mongo_config):
        self._client = MongoClient(
            os.environ["MONGO_SERVICE_SERVICE_HOST"],
            int(os.environ["MONGO_SERVICE_SERVICE_PORT"]),
        )
        if os.environ.get("MONGO_USER"):
            self._client.admin.authenticate(
                os.environ["MONGO_USER"], os.environ["MONGO_PASS"]
            )

        self._walked_hosts = self._client[mongo_config["database"]][
            mongo_config["collection"]
        ]

    def is_connected(self):
        try:
            self._client.admin.command("ismaster")
            return True
        except ConnectionFailure:
            return False

    def contains_host(self, host: str):
        return self._walked_hosts.find({"_id": host}).count()

    def add_host(self, host: str):
        self._walked_hosts.insert_one({"_id": host})

    def delete_host(self, host: str):
        self._walked_hosts.delete_many({"_id": host})

    def clear(self):
        self._walked_hosts.remove()
