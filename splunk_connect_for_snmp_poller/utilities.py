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
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.


import argparse
import logging
import os
import signal
import sys
from enum import Enum

import yaml

logger = logging.getLogger(__name__)


def default_signal_handler(signal_number, frame):
    logger.info(f"Received Signal: {signal_number}")
    sys.exit(signal_number)
    return


def initialize_signals_handler():
    signals_to_catch = (
        signal.SIGHUP,
        signal.SIGINT,
        signal.SIGQUIT,
        signal.SIGQUIT,
        signal.SIGILL,
        signal.SIGTRAP,
        signal.SIGABRT,
        signal.SIGBUS,
        signal.SIGFPE,
        signal.SIGUSR1,
        signal.SIGSEGV,
        signal.SIGUSR2,
        signal.SIGPIPE,
        signal.SIGALRM,
        signal.SIGTERM,
    )
    for one_signal in signals_to_catch:
        signal.signal(one_signal, default_signal_handler)


def parse_command_line_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-l",
        "--loglevel",
        default="debug",
        help="Provide logging level. Example --loglevel debug, default=info",
    )
    parser.add_argument("-c", "--config", default="config.yaml", help="Config File")
    parser.add_argument(
        "-i", "--inventory", default="inventory.csv", help="Inventory Config File"
    )
    parser.add_argument(
        "-r", "--refresh_interval", default="1", help="Refresh Interval of Inventory"
    )
    parser.add_argument(
        "--event_index", default="##EVENTS_INDEX##", help="Event index for polling data"
    )
    parser.add_argument(
        "--metric_index",
        default="##METRICS_INDEX##",
        help="Metric index for polling data",
    )
    parser.add_argument(
        "--meta_index", default="##META_INDEX##", help="Meta index for polling data"
    )
    parser.add_argument(
        "--realtime_task_frequency",
        type=int,
        default=60,
        help="Frequency in seconds for each real-time scheduler task",
    )
    parser.add_argument(
        "--matching_task_frequency",
        type=int,
        default=10,
        help="Frequency in seconds for matching task",
    )
    parser.add_argument(
        "--onetime_task_frequency",
        type=int,
        default=1,
        help="Frequency in seconds for onetime task",
    )
    return parser.parse_args()


def parse_config_file(config_file_path):
    logger.debug(f"Config file is {config_file_path}")
    try:
        with open(config_file_path) as yaml_file:
            server_config = yaml.safe_load(yaml_file)
        logger.debug(f"Server Config is:  {server_config}")
    except Exception as e:
        logger.debug(f"Exception occurred while loading YAML: {e}")

    return server_config


def file_was_modified(file_path, last_mod_time):
    if os.stat(file_path, follow_symlinks=True).st_mtime > last_mod_time:
        logger.info(f"[-] Change in {file_path} detected, reloading")
        # update last_mod_time
        last_mod_time = os.stat(file_path, follow_symlinks=True).st_mtime
        return True, last_mod_time
    return False, last_mod_time


def multi_key_lookup(dictionary, tuple_of_keys):
    from functools import reduce

    try:
        return reduce(dict.get, tuple_of_keys, dictionary)
    except TypeError:
        return None


class OnetimeFlag(str, Enum):
    FIRST_WALK = "first_time"
    AFTER_FAIL = "after_fail"
