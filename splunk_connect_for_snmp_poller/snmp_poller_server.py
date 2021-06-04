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
import logging.config

from splunk_connect_for_snmp_poller.manager.poller import Poller
from splunk_connect_for_snmp_poller.utilities import initialize_signals_handler
from splunk_connect_for_snmp_poller.utilities import parse_command_line_arguments
from splunk_connect_for_snmp_poller.utilities import parse_config_file

logger = logging.getLogger(__name__)


def main():
    logger.info(f"Startup Config")
    args = parse_command_line_arguments()
    logging.getLogger().setLevel(args.loglevel.upper())

    poller_server = Poller(args, parse_config_file(args.config))
    poller_server.run()


if __name__ == "__main__":
    initialize_signals_handler()
    main()
