"""
Tests of disco_aws
"""
from unittest import TestCase
from mock import MagicMock, create_autospec

from disco_aws_automation import DiscoChaos, DiscoAWS, DiscoAutoscale
from test.helpers.patch_disco_aws import (get_default_config_dict,
                                          get_mock_config,
                                          TEST_ENV_NAME)


class DiscoChaosTests(TestCase):
    '''Test DiscoAWS class'''

    def setUp(self):
        config_dict = get_default_config_dict()
        self.chaos = DiscoChaos(config=get_mock_config(config_dict),
                                environment_name=TEST_ENV_NAME,
                                level=25.0, retainage=30.0)
        self.chaos._disco_aws = create_autospec(DiscoAWS)

    def _mock_group(self, capacity=3, tags=None):
        group = MagicMock()
        group.desired_capacity = capacity
        group.instances = []
        group.tags = tags or []
        for _ in xrange(0, capacity):
            instance = MagicMock()
            instance.instance_id = 'i-12345678'
            group.instances.append(instance)
        return group

    def test_get_autoscaling_group_right_params(self):
        '''Test that get_autoscaling_groups makes only valid calls'''
        self.chaos._disco_aws.autoscale = create_autospec(DiscoAutoscale)
        self.chaos._get_autoscaling_groups()
        self.assertEqual(self.chaos._disco_aws.autoscale.get_existing_groups.call_count, 1)

    def test_terminate_right_params(self):
        '''Test that terminate makes only valid calls'''
        self.chaos.terminate([])
        self.assertEqual(self.chaos._disco_aws.terminate.call_count, 1)

    def test_eligible_instances_retainage(self):
        """test that retainage reserves sufficient instances"""
        self.chaos._groups = [self._mock_group()]
        self.assertEqual(len(self.chaos._termination_eligible_instances()), 2)

    def test_eligible_instances_tags(self):
        """test that tags are checked for autoscaling groups"""
        ftags = [MagicMock()]
        ftags[0].key = 'chaos'
        ftags[0].value = 'False'
        ttags = [MagicMock()]
        ttags[0].key = 'chaos'
        ttags[0].value = 'yes'
        self.chaos._groups = [self._mock_group(30, ftags), self._mock_group(10), self._mock_group(10, ttags)]
        self.assertEqual(len(self.chaos._termination_eligible_instances()), 14)

    def test_eligible_instances_retainage_zero(self):
        """Test that retainage of zero retatins nothing"""
        config_dict = get_default_config_dict()
        self.chaos = DiscoChaos(config=get_mock_config(config_dict),
                                environment_name=TEST_ENV_NAME,
                                level=25.0, retainage=0.0)
        self.chaos._groups = [self._mock_group()]
        self.assertEqual(len(self.chaos._termination_eligible_instances()), 3)

    def _fake_instances(self, _filters=None, instance_ids=None):
        return instance_ids

    def test_level_with_small_list(self):
        """At least one instance killed when instance list is small"""
        self.chaos._groups = [self._mock_group()]
        self.chaos._disco_aws.instances = self._fake_instances
        self.assertEqual(len(self.chaos.get_instances_to_terminate()), 1)

    def test_level_with_empty_list(self):
        """No instance killed when instance list is empty"""
        self.chaos._groups = []
        self.chaos._disco_aws.instances = self._fake_instances
        self.assertEqual(len(self.chaos.get_instances_to_terminate()), 0)

    def test_level_with_large_list(self):
        """Right percentage of instances killed when instance list is large"""
        self.chaos._groups = [self._mock_group(100)]
        self.chaos._disco_aws.instances = self._fake_instances
        self.assertEqual(len(self.chaos.get_instances_to_terminate()), int(25))
