import argparse
import logging.config

import yaml

from splunk_connect_for_snmp_poller.manager.poller import Poller
from splunk_connect_for_snmp_poller.utilities import initialize_signals_handler

logger = logging.getLogger(__name__)


def main():
    logger.info(f"Startup Config")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-l",
        "--loglevel",
        default="warning",
        help="Provide logging level. Example --loglevel debug, default=warning",
    )
    parser.add_argument(
        "-p", "--port", default="2062", help="Port used to accept poller", type=int
    )
    parser.add_argument("-c", "--config", default="config.yaml", help="Config File")
    args = parser.parse_args()

    log_level = args.loglevel.upper()
    config_file = args.config

    logging.getLogger().setLevel(log_level)
    logger.info(f"Log Level is {log_level}")
    logger.info(f"Config file is {config_file}")

    logger.info("Completed Argument parsing")

    with open(config_file, "r") as yamlfile:
        server_config = yaml.load(yamlfile, Loader=yaml.FullLoader)

    logger.debug(f"Server Config is:  {server_config}")

    my_poller = Poller(args, server_config)
    my_poller.run()


if __name__ == "__main__":
    initialize_signals_handler()
    main()
