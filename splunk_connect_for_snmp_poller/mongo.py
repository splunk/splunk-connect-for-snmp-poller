from pymongo import MongoClient

client = MongoClient(port=27017)
walked_hosts = client.snmp_poller.snmp_walk


def contains_host(host):
    return walked_hosts.find({'_id': host}).count()


def add_host(host):
    walked_hosts.insert_one({'_id': host})
