"""
Some mocking to make writing unit tests for DiscoAWS easier.  To use decorate your
test methods with @patch_disco_aws and add **kwargs to your test signatures.
The mocks will be provided as keyword arguments starting with mock.  For example:

    >>> from unittest import TestCase
    >>> from disco_aws_automation import DiscoAWS
    >>> class YourTestClass(TestCase):
    ...     @patch_disco_aws
    ...     def test_your_stuff(self, mock_config, **kwargs):
    ...         aws = DiscoAWS(config=mock_config, environment_name="somename")
    ...         # test some stuff

    or you can replace the config with your own

    >>> from unittest import TestCase
    >>> class YourTestClass(TestCase):
    ...     @patch_disco_aws
    ...     def test_more_stuff(self, **kwargs):
    ...         config_dict = get_default_config_dict()
    ...         config_dict["section"]["key"] = "val"
    ...         aws = DiscoAWS(config=get_mock_config(config_dict), environment_name="somename")
    ...         # test more stuff

See PATCH_LIST and patch_disco_aws for available mocks and their names.
"""
from ConfigParser import NoSectionError, NoOptionError

from mock import Mock, patch
from moto import mock_ec2, mock_s3, mock_autoscaling, mock_route53, mock_elb

from test.helpers.patcher import patcher

TEST_ENV_NAME = "unittestenv"
PATCH_LIST = [patch("disco_aws_automation.disco_aws.wait_for_state",
                    kwargs_field="mock_wait"),
              patch("disco_aws_automation.disco_vpc.DiscoVPC.fetch_environment",
                    kwargs_field="mock_fetch_env")]


def get_default_config_dict():
    '''Starting Configuration for a hostclass'''
    return {"mhcunittest": {"subnet": "intranet",
                            "security_group": "intranet",
                            "ssh_key_name": "unittestkey",
                            "instance_profile_name": "unittestprofile",
                            "public_ip": "False",
                            "ip_address": None,
                            "eip": None,
                            "route": None,
                            "source_dest_check": "yes"},
            "disco_aws": {"default_meta_network": "intranet",
                          "project_name": "unittest",
                          "default_enable_proxy": "True",
                          "http_proxy_hostclass": "mhchttpproxy",
                          "zookeeper_hostclass": "mhczookeeper",
                          "logger_hostclass": "mhclogger",
                          "logforwarder_hostclass": "mhclogforwarder",
                          "default_smoketest_termination": "True"}}


def get_mock_config(config_dict=None):
    '''
    Returns a config class which returns the contents of either the
    default dictionary or a dictionary passed in.
    The format of the dictionary is
    {"section": {"key" : "value"}
    '''
    mock_config = Mock()
    config_dict = config_dict if config_dict else get_default_config_dict()

    def _mock_config_get(section, key):
        if section not in config_dict:
            raise NoSectionError(section)
        if key not in config_dict[section]:
            raise NoOptionError(key, section)
        return config_dict[section][key]

    def _mock_config_has(section, key):
        return (section in config_dict) and (key in config_dict[section])

    def _mock_config_items(section):
        return config_dict[section].iteritems() if config_dict.get(section) else []

    mock_config.sections.return_value = config_dict.keys()
    mock_config.get.side_effect = _mock_config_get
    mock_config.has_option.side_effect = _mock_config_has

    mock_config.items.side_effect = _mock_config_items

    return mock_config


patch_disco_aws = patcher(patches=PATCH_LIST,
                          decorators=[mock_ec2, mock_s3, mock_autoscaling, mock_route53, mock_elb],
                          mock_config=get_mock_config())
