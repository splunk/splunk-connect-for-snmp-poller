from unittest import TestCase
from pysnmp.hlapi import ObjectIdentity, ObjectType

from splunk_connect_for_snmp_poller.manager.task_utilities import (
    VarbindCollection
)

from splunk_connect_for_snmp_poller.manager.tasks import (
    sort_varbinds
)


def cast_helper(varbinds):
    return [ObjectType(ObjectIdentity(el)) for el in varbinds]


class TestTasks(TestCase):

    def test_sort_varbinds_get(self):
        varbinds = ['1.3.6.1.2.1.2.1', '1.3.6.1.2.1.2.2', ['SNMPv2-MIB', 'sysUpTime', 0]]
        get_varbinds_result = VarbindCollection(bulk=[], get=cast_helper(varbinds))
        actual_result = sort_varbinds(varbinds)
        self.assertEqual(actual_result.__dict__, get_varbinds_result.__dict__)

    def test_sort_varbinds_bulk(self):
        varbinds = ['1.3.6.1.2.1.2.*', '1.3.6.1.2.1.2.*', ['CISCO-FC-MGMT-MIB', 'cfcmPortLcStatsEntry']]
        bulk_varbinds_result = VarbindCollection(bulk=cast_helper(varbinds), get=[])
        actual_result = sort_varbinds(varbinds)
        self.assertEqual(actual_result.__dict__, bulk_varbinds_result.__dict__)

    def test_sort_varbinds_bulk_get(self):
        varbinds = ['1.3.6.1.2.1.2.*', '1.3.6.1.2.1.2.*', ['CISCO-FC-MGMT-MIB', 'cfcmPortLcStatsEntry'],
                    '1.3.6.1.2.1.2.1', '1.3.6.1.2.1.2.2', ['SNMPv2-MIB', 'sysUpTime', 0]]
        varbinds_get = cast_helper(['1.3.6.1.2.1.2.1', '1.3.6.1.2.1.2.2', ['SNMPv2-MIB', 'sysUpTime', 0]])
        varbinds_bulk = cast_helper(['1.3.6.1.2.1.2.*', '1.3.6.1.2.1.2.*', ['CISCO-FC-MGMT-MIB',
                                                                            'cfcmPortLcStatsEntry']])
        varbinds_result = VarbindCollection(bulk=varbinds_bulk, get=varbinds_get)
        actual_result = sort_varbinds(varbinds)
        self.assertEqual(actual_result.__dict__, varbinds_result.__dict__)

    def test_sort_varbinds_empty(self):
        varbinds = []
        varbinds_result = VarbindCollection(bulk=[], get=[])
        actual_result = sort_varbinds(varbinds)
        self.assertEqual(actual_result.__dict__, varbinds_result.__dict__)
