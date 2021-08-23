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

import os

from jsoncomment import JsonComment


def load_test_data(data_file_path):
    if data_file_path and os.path.exists(data_file_path):
        with open(data_file_path) as sample_simulator_walk_data:
            walk_data = JsonComment().load(sample_simulator_walk_data)
            return walk_data
    return None


def fake_walk_handler(simulator_ifmib_walk_data):
    yield from simulator_ifmib_walk_data


def file_data_path(data_file_name):
    current_dir = os.getcwd()
    relative_data_file_path = os.path.join("mib_walk_data", data_file_name)
    if current_dir.endswith("tests"):
        file_path = os.path.join(current_dir, relative_data_file_path)
    else:
        file_path = os.path.join(current_dir, "tests", relative_data_file_path)
    return file_path


if __name__ == "__main__":
    file_path = "mib_walk_data/if_mib_walk.json"

    for metric in fake_walk_handler(load_test_data(file_path)):
        print(f"{metric}")
