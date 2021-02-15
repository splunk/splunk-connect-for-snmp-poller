if __name__ == '__main__':
    from splunk_connect_for_snmp_poller.manager.tasks import add
    print('Trying to schedule a task!')
    result = add.delay(2, 3)
    value = result.get(timeout=1)
    print(f'The result is {value}')