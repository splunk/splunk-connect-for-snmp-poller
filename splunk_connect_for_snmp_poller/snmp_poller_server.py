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
