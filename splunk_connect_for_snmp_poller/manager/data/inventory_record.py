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
import json
from dataclasses import dataclass

from splunk_connect_for_snmp_poller.manager.data.event_builder import EventField


@dataclass
class InventoryRecord:
    host: str
    version: str
    community: str
    profile: str
    frequency_str: str

    def to_json(self) -> str:
        return json.dumps(self, default=lambda o: o.__dict__)

    def extend_dict_with_provided_data(
        self, fields: dict, additional_metric_fields: list
    ) -> dict:
        if (
            additional_metric_fields
            and EventField.PROFILE.value in additional_metric_fields
        ):
            fields[EventField.PROFILE.value] = self.profile

        return fields

    @staticmethod
    def from_json(ir_json: str):
        ir_dict = json.loads(ir_json)
        return InventoryRecord(**ir_dict)
