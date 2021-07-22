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

import json
import os


def load_test_data(data_file_path):
    if data_file_path and os.path.exists(data_file_path):
        with open(data_file_path, "r") as sample_simulator_walk_data:
            walk_data = json.load(sample_simulator_walk_data)
            return walk_data
    return None


def fake_walk_handler(simulator_ifmib_walk_data):
    for translated_metric in simulator_ifmib_walk_data:
        yield translated_metric


if __name__ == "__main__":
    file_path = "mib_walk_data/if_mib_walk.json"

    for metric in fake_walk_handler(load_test_data(file_path)):
        print(f"{metric}")
