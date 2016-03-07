"""
Tests for secure configuration
"""
from ConfigParser import ConfigParser
from unittest import TestCase
import logging
import re
import subprocess
import os

# Don't freak out about regular expression in string (for grep)
# pylint: disable=W1401

SSH_PORT = 22


class SecureConfig(TestCase):
    """
    Test to ensure we don't shoot ourselves in the foot
    """

    def setUp(self):
        self._old_dir = os.getcwd()
        os.chdir(os.getenv("ASIAQ_CONFIG", "."))

    def tearDown(self):
        os.chdir(self._old_dir)

    def test_log_level_is_safe(self):
        """
        Logging config does not contain debug logging
        see https://docs.python.org/2/library/logging.html
        """
        cmd = 'find . -type f -name "config.ini" | xargs grep -i "level.*=" | grep "\(NOTSET\|DEBUG\)"'
        self.assertNotEqual(subprocess.call(cmd, shell=True), 0)

    def test_yum_update(self):
        """
        Ensure yum update is present in CentOS phase1 and not commented out
        """
        self.assertEqual(subprocess.call(["grep", '^yum update -y', "init/centos6_phase1.sh"]), 0)
        self.assertEqual(subprocess.call(["grep", '^yum update -y', "init/centos7_phase1.sh"]), 0)

    def test_apt_update(self):
        """
        Ensure apt-get update is present in Ubuntu phase1 and not commented out
        """
        self.assertEqual(subprocess.call(["grep", '^apt-get update', "init/ubuntu_phase1.sh"]), 0)

    def test_apt_upgrade(self):
        """
        Ensure apt-get upgrade is present in Ubuntu phase1 and not commented out
        """
        self.assertEqual(subprocess.call(["grep", '^apt-get upgrade', "init/ubuntu_phase1.sh"]), 0)

    def _port_in_sg_rule(self, needle, haystack):
        """
        True if needle if part of haystack port specification
        """
        for ports in haystack:
            ports = ports.split(":")
            if len(ports) == 1 and needle == int(ports[0]):
                return True
            if len(ports) > 1 and needle >= int(ports[0]) and needle <= int(ports[1]):
                return True
        return False

    def _allowed_ips(self):
        """
        Return list of ips which ought to be able to ssh to production env
        """
        daws_config_file = "disco_aws.ini"
        daws_config = ConfigParser()
        daws_config.read(daws_config_file)
        deployenator = "mhcdiscodeployenator"

        option = "eip@deploy"
        if daws_config.has_section(deployenator) and daws_config.has_option(deployenator, option):
            return [daws_config.get(deployenator, option)]
        else:
            return []

    def _prod_sg_rules(self):
        """
        Return sg rules for all production networks
        """
        vpc_config_file = "disco_vpc.ini"
        vpc_config = ConfigParser()
        vpc_config.read(vpc_config_file)
        prod_section = "envtype:production"

        self.assertTrue(vpc_config.has_section(prod_section))

        # Since we only have one prod we shouldn't need duplicate config
        # but if this changes in the future we'll need to adjust the check
        # to inspect env and envtypes.
        self.assertFalse(vpc_config.has_section("env:prod"))

        sg_rule_names = [name for name in vpc_config.options(prod_section) if name.endswith("sg_rules")]
        return [vpc_config.get(prod_section, name) for name in sg_rule_names]

    def test_prod_ssh_sg_rules(self):
        """
        Ensure that prod firewall rules don't allow ssh traffic.
        """

        sg_rules = ",".join(self._prod_sg_rules())
        allowed_ips = self._allowed_ips()

        # We only allow port 22, TCP open from non-ip sources (other subnets)
        # or deployenator host
        source_regex = re.compile(r'[a-zA-Z]+[0-9a-zA-Z]+')
        for sg_rule in sg_rules.split(","):
            sg_rule = sg_rule.split()
            source = sg_rule[1]
            # ssh protocol is 'tcp' or protocol number 6.
            if (sg_rule[0] == 'tcp' or sg_rule[0] == '6') and \
                    self._port_in_sg_rule(SSH_PORT, sg_rule[2:]) and not source_regex.search(source):
                try:
                    self.assertIn(source.split("/")[0], allowed_ips)
                except AssertionError:
                    logging.exception("Production firewall has port 22 open to invalid host.")
                    raise
