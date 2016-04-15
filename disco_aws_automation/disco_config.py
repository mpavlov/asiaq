import boto3

from . import read_config
from .disco_constants import DEFAULT_CONFIG_SECTION
from .disco_aws_util import is_truthy


class DiscoAWSConfigReader(object):
    """Class for reading all AWS configuration information"""

    def __init__(self, environment_name=None):
        self._config_aws = read_config()
        self._config_vpc = read_config("disco_vpc.ini")
        self.environment_name = environment_name or self._config_aws.get("disco_aws", "default_environment")
        self.env_specific_suffix = "@{}".format(environment_name)
        self._session = None  # Lazily initialized
        self._region = None  # Lazily initialized
        self._account_id = None  # Lazily initialized

    @property
    def session(self):
        if not self._session:
            self._session = boto3.session.Session()
        return self._session

    @property
    def account_id(self):
        if not self._account_id:
            self._account_id = boto3.resource('iam').CurrentUser().arn.split(':')[4]
        return self._account_id

    @property
    def region(self):
        if not self._region:
            # Doing this requires boto3>=1.2.4
            # Could use undocumented and unsupported workaround for earlier versions:
            # session._session.get_config_variable('region')
            self._region = self.session.region_name
        return self._region

    def get_es_config(self):
        proxy_hostclass = self.get_aws_option('http_proxy_hostclass')
        es_config = {'instance_type': self.get_vpc_option('es_instance_type', 'm3.medium.elasticsearch'),
                     'instance_count': int(self.get_vpc_option('es_instance_count', 1)),
                     'dedicated_master': is_truthy(self.get_vpc_option('es_dedicated_master', "False")),
                     'dedicated_master_type': self.get_vpc_option('es_dedicated_master_type', None),
                     'dedicated_master_count': int(self.get_vpc_option('es_dedicated_master_count', "0")),
                     'zone_awareness': is_truthy(self.get_vpc_option('es_zone_awareness', "False")),
                     'ebs_enabled': is_truthy(self.get_vpc_option('es_ebs_enabled', "False")),
                     'volume_type': self.get_vpc_option('es_volume_type', 'standard'),
                     'volume_size': int(self.get_vpc_option('es_volume_size', 10)),
                     'iops': int(self.get_vpc_option('es_iops', 1000)),
                     'snapshot_start_hour': int(self.get_vpc_option('es_snapshot_start_hour', 5)),
                     'proxy_ip': self.get_hostclass_option('eip', proxy_hostclass),
                     'region': self.region,
                     'domain_name': self.get_aws_option('domain_name'),
                     'account_id': self.account_id,
                     'environment_name': self.environment_name}

        return es_config

    def get_vpc_option(self, option, default=None):
        '''Returns appropriate configuration for the current environment'''
        env_section = "env:{0}".format(self.environment_name)
        envtype_section = "envtype:{0}".format(self.environment_name)
        envtype_sandbox_section = "envtype:{0}".format("sandbox")
        peering_section = "peerings"

        value = None

        if self._config_vpc.has_option(env_section, option):
            value = self._config_vpc.get(env_section, option)
        elif self._config_vpc.has_option(envtype_section, option):
            value = self._config_vpc.get(envtype_section, option)
        elif self._config_vpc.has_option(envtype_sandbox_section, option):
            value = self._config_vpc.get(envtype_sandbox_section, option)
        elif self._config_vpc.has_option(peering_section, option):
            value = self._config_vpc.get(peering_section, option)

        return value or default

    def get_aws_option(self, option, section=DEFAULT_CONFIG_SECTION, default=None):
        """Get a value from the config"""
        env_option = "{0}@{1}".format(option, self.environment_name)
        default_option = "default_{0}".format(option)
        default_env_option = "default_{0}".format(env_option)

        value = None

        if self._config_aws.has_option(section, env_option):
            value = self._config_aws.get(section, env_option)
        if self._config_aws.has_option(section, option):
            value = self._config_aws.get(section, option)
        elif self._config_aws.has_option(DEFAULT_CONFIG_SECTION, default_env_option):
            value = self._config_aws.get(DEFAULT_CONFIG_SECTION, default_env_option)
        elif self._config_aws.has_option(DEFAULT_CONFIG_SECTION, default_option):
            value = self._config_aws.get(DEFAULT_CONFIG_SECTION, default_option)

        return value or default

    def get_hostclass_option(self, option, hostclass, default=None):
        """Fetch a hostclass configuration option, if it does not exist get the default"""
        return self.get_aws_option(option, hostclass, default)
