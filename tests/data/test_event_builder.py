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

import logging
import time
from unittest import TestCase

from splunk_connect_for_snmp_poller.manager.data.event_builder import (
    EventBuilder,
    EventField,
)

logger = logging.getLogger(__name__)


class TestEventBuilder(TestCase):
    def test_event_build_for_normal_event(self):
        """
        Test that checks if EventBuilder correctly builds dict for normal event
        """
        timer = time.time()
        expected = {
            "time": timer,
            "sourcetype": "sc4snmp:meta",
            "host": "ourhost",
            "index": "meta_index",
            "event": "binds",
        }

        builder = EventBuilder()
        builder.add(EventField.TIME, timer)
        builder.add(EventField.HOST, "ourhost")
        builder.add(EventField.INDEX, "meta_index")
        builder.add(EventField.SOURCETYPE, "sc4snmp:meta")
        builder.add(EventField.EVENT, "binds")

        self.assertDictEqual(expected, builder.build())

    def test_event_build_for_walk_event(self):
        """
        Test that checks if EventBuilder correctly builds dict for walk event
        """
        timer = time.time()
        expected = {
            "time": timer,
            "sourcetype": "sc4snmp:walk",
            "host": "ourhost",
            "index": "meta_index",
            "event": "binds",
        }

        builder = EventBuilder()
        builder.add(EventField.TIME, timer)
        builder.add(EventField.HOST, "ourhost")
        builder.add(EventField.INDEX, "meta_index")
        builder.add(EventField.SOURCETYPE, "sc4snmp:meta")
        builder.add(EventField.EVENT, "binds")

        builder.is_one_time_walk(True)

        self.assertDictEqual(expected, builder.build())

    def test_event_build_with_added_fields(self):
        """
        Test that checks if EventBuilder correctly builds dict with fields
        """
        timer = time.time()
        some_field_ = {"some": "field"}
        expected = {
            "time": timer,
            "sourcetype": "sc4snmp:meta",
            "host": "ourhost",
            "index": "meta_index",
            "event": "binds",
            "fields": some_field_,
        }

        builder = EventBuilder()
        builder.add(EventField.TIME, timer)
        builder.add(EventField.HOST, "ourhost")
        builder.add(EventField.INDEX, "meta_index")
        builder.add(EventField.SOURCETYPE, "sc4snmp:meta")
        builder.add(EventField.EVENT, "binds")
        builder.add_fields(some_field_)

        self.assertDictEqual(expected, builder.build())
