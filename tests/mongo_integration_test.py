from splunk_connect_for_snmp_poller.mongo import WalkedHostsRepository


# TODO as for now this is just a demo on how to use WalkedHostsRepository
# TODO final version should use fixures to run MongoDB in Docker
def main():
    mongo_config = {'host': 'localhost', 'port': 27017, 'database': 'snmp_poller', 'collection': 'walked_hosts'}

    mongo = WalkedHostsRepository(mongo_config)

    mongo.clear()
    mongo.add_host('192.168.0.2')
    print(mongo.contains_host('192.168.0.2'))

    mongo.delete_host('192.168.0.2')
    print(mongo.contains_host('192.168.0.2'))


if __name__ == '__main__':
    main()
