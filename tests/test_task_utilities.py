from unittest import TestCase

from splunk_connect_for_snmp_poller.manager.task_utilities import (
    is_metric_data,
    parse_port,
)


class ObjectTypeMock:
    def __init__(self, value):
        self._value = value

    def prettyPrint(self):
        return self._value


class TestTaskUtilities(TestCase):
    def test_metric_for_integer(self):
        self.assertTrue(is_metric_data([("some_name", ObjectTypeMock("1"))]))

    def test_metric_for_negative_integer(self):
        self.assertTrue(is_metric_data([("some_name", ObjectTypeMock("-5"))]))

    def test_metric_for_float(self):
        self.assertTrue(is_metric_data([("some_name", ObjectTypeMock("2.0"))]))

    def test_metric_for_negative_float(self):
        self.assertTrue(is_metric_data([("some_name", ObjectTypeMock("-2.0"))]))

    def test_metric_for_zero(self):
        self.assertTrue(is_metric_data([("some_name", ObjectTypeMock("0"))]))

    def test_metric_for_string(self):
        self.assertFalse(is_metric_data([("some_name", ObjectTypeMock("asdad"))]))

    def test_port_parse_with_default_port(self):
        host, port = parse_port("192.168.0.13")
        self.assertEqual(host, "192.168.0.13")
        self.assertEqual(port, 161)

    def test_port_parse_with_specified_port(self):
        host, port = parse_port("192.168.0.13:765")
        self.assertEqual(host, "192.168.0.13")
        self.assertEqual(port, "765")
