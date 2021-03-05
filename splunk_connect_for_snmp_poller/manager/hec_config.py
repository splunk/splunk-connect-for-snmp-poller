import logging
import os

logger = logging.getLogger(__name__)

# TODO
# Should customer create metric token all the time during setup, or is the metric token feature optional


class HecConfiguration:
    endpoints_env_variable_name = "SPLUNK_HEC_URL"
    authentication_token_env_variable_name = "SPLUNK_HEC_TOKEN"
    authentication_metric_token_env_variable_name = "SPLUNK_HEC_METRIC_TOKEN"
    enable_ssl_env_variable_name = "SPLUNK_HEC_TLS_VERIFY"

    def __init__(self):
        urls = os.environ.get(HecConfiguration.endpoints_env_variable_name)
        if urls is None:
            raise ValueError(
                f"{HecConfiguration.endpoints_env_variable_name} environment variable undefined"
            )
        self._urls_list = urls.split()

        authentication_token = os.environ.get(
            HecConfiguration.authentication_token_env_variable_name
        )
        if authentication_token is None:
            raise ValueError(
                f"{HecConfiguration.authentication_token_env_variable_name} environment variable undefined"
            )
        self._authentication_token = authentication_token
        
        # The metric token is optional
        authentication_metric_token = os.environ.get(
            HecConfiguration.authentication_metric_token_env_variable_name
        )
        self._authentication_metric_token = authentication_metric_token

        enable_ssl = os.environ.get(HecConfiguration.enable_ssl_env_variable_name)
        if enable_ssl is None:
            raise ValueError(
                f"{HecConfiguration.enable_ssl_env_variable_name} environment variable undefined"
            )
        self._enable_ssl = True if enable_ssl.lower() == "yes" else False

    def get_endpoints(self):
        return self._urls_list

    def get_authentication_token(self):
        return self._authentication_token
    
    def get_authentication_metric_token(self):
        return self._authentication_metric_token

    def is_ssl_enabled(self):
        return self._enable_ssl
