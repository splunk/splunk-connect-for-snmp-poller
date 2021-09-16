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
from enum import Enum
from typing import Any, Dict

from celery.utils.log import get_logger

logger = get_logger(__name__)


class EventBuilder:
    def __init__(self) -> None:
        self.data: Dict = {}

    def add(self, field, part: Any) -> None:
        self.data[field.value] = part

    def is_one_time_walk(self, one_time_flag: bool) -> None:
        if one_time_flag:
            self.data[EventField.SOURCETYPE.value] = EventType.WALK.value

    def build(self) -> dict:
        logger.debug("--------data------\n%s", self.data)
        return self.data


class EventField(Enum):
    TIME = "time"
    SOURCETYPE = "sourcetype"
    HOST = "host"
    INDEX = "index"
    EVENT = "event"
    FREQUENCY = "frequency"
    PROFILE = "profile"
    FIELDS = "fields"


class EventType(Enum):
    EVENT = "sc4snmp:meta"
    METRIC = "metric"
    WALK = "sc4snmp:walk"
    ERROR = "sc4snmp:error"
