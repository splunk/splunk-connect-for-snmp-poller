from pymongo import MongoClient
from pymongo.errors import ConnectionFailure


class WalkedHostsRepository:
    def __init__(self, mongo_config):
        self._client = MongoClient(host=mongo_config['host'], port=mongo_config['port'])
        self._walked_hosts = self._client[mongo_config['database']][mongo_config['collection']]

    def is_connected(self):
        try:
            self._client.admin.command('ismaster')
            return True
        except ConnectionFailure:
            return False

    def contains_host(self, host):
        return self._walked_hosts.find({'_id': host}).count()

    def add_host(self, host):
        self._walked_hosts.insert_one({'_id': host})

    def delete_host(self, host):
        self._walked_hosts.delete_many({'_id': host})

    def clear(self):
        self._walked_hosts.remove()
