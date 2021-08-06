from unittest import TestCase
from pysnmp.hlapi import ObjectIdentity, ObjectType
import collections

from splunk_connect_for_snmp_poller.manager.task_utilities import (
    VarbindCollection
)

from splunk_connect_for_snmp_poller.manager.tasks import (
    sort_varbinds
)

compare = lambda x, y: collections.Counter(x) == collections.Counter(y)

def cast_helper(varbinds):
    result = []
    for el in varbinds:
        if isinstance(el, list):
            result.append(ObjectType(ObjectIdentity(el[0], el[1])))
        else:
            result.append(ObjectType(ObjectIdentity(el)))
    return result


class TestTasks(TestCase):

    def test_sort_varbinds_get(self):
        varbinds = ['1.3.6.1.2.1.2.2', '1.3.6.1.2.1.2.3', ['SNMPv2-MIB', 'sysUpTime', 0]]
        get_varbinds_result = VarbindCollection(bulk=[], get=['1.3.6.1.2.1.2.2', '1.3.6.1.2.1.2.3',
                                                                          '1.3.6.1.2.1.1.3.0'])
        actual_result = sort_varbinds(varbinds)
        self.assertEqual(sorted(actual_result.get), sorted(get_varbinds_result.get))

    def test_sort_varbinds_bulk(self):
        varbinds = [['CISCO-FC-MGMT-MIB', 'cfcmPortLcStatsEntry']]
        bulk_varbinds_result = VarbindCollection(bulk=cast_helper([['CISCO-FC-MGMT-MIB', 'cfcmPortLcStatsEntry']]), get=[])
        actual_result = sort_varbinds(varbinds)
        self.assertEqual(str(actual_result.bulk), str(bulk_varbinds_result.bulk))

    def test_sort_varbinds_bulk_star(self):
        varbinds = ['1.3.6.1.2.1.2.*']
        bulk_varbinds_result = VarbindCollection(bulk=cast_helper(['1.3.6.1.2.1.2']), get=[])
        actual_result = sort_varbinds(varbinds)
        self.assertEqual(str(actual_result.bulk), str(bulk_varbinds_result.bulk))

    def test_sort_varbinds_bulk_get(self):
        varbinds = ['1.3.6.1.2.1.2.*', '1.3.6.1.2.1.2.1']
        varbinds_get = ['1.3.6.1.2.1.2.1']
        varbinds_bulk = cast_helper(['1.3.6.1.2.1.2'])
        varbinds_result = VarbindCollection(bulk=varbinds_bulk, get=varbinds_get)
        actual_result = sort_varbinds(varbinds)
        self.assertEqual(str(actual_result.bulk), str(varbinds_result.bulk))
        self.assertEqual(str(actual_result.get), str(varbinds_result.get))

    def test_sort_varbinds_empty(self):
        varbinds = []
        varbinds_result = VarbindCollection(bulk=[], get=[])
        actual_result = sort_varbinds(varbinds)
        self.assertEqual(actual_result.__dict__, varbinds_result.__dict__)
