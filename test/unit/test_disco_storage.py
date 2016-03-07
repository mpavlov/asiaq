"""
Tests of disco_aws
"""
from unittest import TestCase
import random

import dateutil.parser as dateparser
from mock import MagicMock
from moto import mock_ec2

from disco_aws_automation import DiscoStorage


class DiscoStorageTests(TestCase):
    '''Test DiscoStorage class'''

    @mock_ec2
    def setUp(self):
        self.storage = DiscoStorage()

    def test_is_ebs_optimized(self):
        '''is_ebs_optimized works'''
        self.assertTrue(self.storage.is_ebs_optimized("m4.xlarge"))
        self.assertFalse(self.storage.is_ebs_optimized("t2.micro"))

    @mock_ec2
    def test_get_latest_snapshot_no_snap(self):
        '''get_latest_snapshot() returns None if no snapshots exist for hostclass'''
        self.assertIsNone(self.storage.get_latest_snapshot("mhcfoo"))

    def mock_snap(self, hostclass, when=None):
        '''Creates MagicMock for a snapshot'''
        ret = MagicMock()
        ret.tags = {"hostclass": hostclass}
        ret.start_time = when if when else dateparser.parse("2016-01-19 16:38:48+00:00")
        ret.id = 'snap-' + str(random.randrange(0, 9999999))
        ret.volume_size = random.randrange(1, 9999)
        return ret

    def test_get_latest_snapshot_with_snaps(self):
        '''get_latest_snapshot() returns correct snapshot if many exist'''
        snap_list = [
            self.mock_snap("mhcfoo", dateparser.parse("2016-01-15 16:38:48+00:00")),
            self.mock_snap("mhcfoo", dateparser.parse("2016-01-19 16:38:48+00:00")),
            self.mock_snap("mhcfoo", dateparser.parse("2016-01-17 16:38:48+00:00"))]
        self.storage.connection.get_all_snapshots = MagicMock(return_value=snap_list)
        self.assertEqual(self.storage.get_latest_snapshot("mhcfoo"), snap_list[1])

    def test_create_snapshot_bdm_syntax(self):
        '''create_snapshot_bdm() calls functions with correct syntax'''
        dev = self.storage.create_snapshot_bdm(self.mock_snap("mhcbar"), 5)
        self.assertEqual(dev.iops, 5)
