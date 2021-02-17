import argparse
import logging
import signal

import yaml

logger = logging.getLogger(__name__)


def default_signal_handler(signal_number, frame):
    logger.info(f'Received Signal: {signal_number}')
    return


def initialize_signals_handler():
    signals_to_catch = (
        signal.SIGHUP, signal.SIGINT, signal.SIGQUIT, signal.SIGQUIT, signal.SIGILL, signal.SIGTRAP, signal.SIGABRT,
        signal.SIGBUS, signal.SIGFPE, signal.SIGUSR1, signal.SIGSEGV, signal.SIGUSR2, signal.SIGPIPE, signal.SIGALRM,
        signal.SIGTERM)
    for one_signal in signals_to_catch:
        signal.signal(one_signal, default_signal_handler)


def parse_command_line_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-l', '--loglevel', default='debug',
                        help='Provide logging level. Example --loglevel debug, default=warning')
    parser.add_argument('-p', '--port', default='2062', help='Port used to accept poller', type=int)
    parser.add_argument('-c', '--config', default='config.yaml', help='Config File')
    parser.add_argument('-i', '--inventory', default='inventory.csv', help='Inventory Config File')

    return parser.parse_args()


def parse_config_file(config_file_path):
    logger.info(f'Config file is {config_file_path}')
    with open(config_file_path, 'r') as yaml_file:
        server_config = yaml.load(yaml_file, Loader=yaml.FullLoader)
    logger.debug(f'Server Config is:  {server_config}')

    return server_config
