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

    def contains_host(self, host):
        return self._walked_hosts.find({"_id": host}).count()

    def add_host(self, host):
        self._walked_hosts.insert_one({"_id": host})

    def delete_host(self, host):
        self._walked_hosts.delete_many({"_id": host})

    def clear(self):
        self._walked_hosts.remove()
