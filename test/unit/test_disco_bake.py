"""
Tests of disco_bake
"""
import random
from unittest import TestCase

import boto.ec2.instance
from mock import MagicMock, Mock, PropertyMock, ANY, create_autospec

from disco_aws_automation import DiscoBake, AMIError


class DiscoBakeTests(TestCase):
    '''Test DiscoBake class'''

    def mock_ami(self, name, stage=None, product_line=None, state=u'available'):
        '''Create a mock AMI'''
        def _mock_get(tag_name, default=None):
            if tag_name == "productline":
                return product_line if product_line else default
            if tag_name == "stage":
                return stage if stage else default

        ami = create_autospec(boto.ec2.image.Image)
        ami.name = name
        ami.tags = MagicMock(get=_mock_get)
        ami.id = 'ami-' + ''.join(random.choice("0123456789abcdef") for _ in range(8))
        ami.state = state
        return ami

    def add_ami(self, name, stage, product_line=None, state=u'available'):
        '''Add one Instance AMI Mock to an AMI list'''
        ami = self.mock_ami(name, stage, product_line, state)
        assert ami.name == name
        assert ami.tags.get("stage") == stage
        assert ami.tags.get("productline") == product_line
        self._amis.append(ami)
        self._amis_by_name[ami.name] = ami
        return ami

    def setUp(self):
        self._bake = DiscoBake(config=MagicMock(), connection=MagicMock())
        self._bake.promote_ami = MagicMock()
        self._bake.ami_stages = MagicMock(return_value=['untested', 'failed', 'tested'])
        self._bake.get_ami_creation_time = DiscoBake.extract_ami_creation_time_from_ami_name
        self._amis = []
        self._amis_by_name = {}
        self.add_ami('mhcfoo 1', 'untested', 'astro')
        self.add_ami('mhcbar 2', 'tested')
        self.add_ami('mhcfoo 4', 'tested', 'astro')
        self.add_ami('mhcfoo 5', 'failed')
        self.add_ami('mhcbar 1', 'tested', 'someone_else')
        self._bake.get_amis = MagicMock(return_value=self._amis)

    def test_get_phase1_ami_id_success(self):
        '''Test that get_phase1_ami_id uses find_ami properly on success'''
        ami = Mock()
        type(ami).id = PropertyMock(return_value='ami-abcd1234')
        self._bake.ami_stages = Mock(return_value=['a', 'b', 'c'])
        self._bake.find_ami = Mock(return_value=ami)
        self._bake.hc_option = Mock(return_value="mhcphase1")
        self.assertEqual("ami-abcd1234", self._bake._get_phase1_ami_id(hostclass="mhcntp"))
        self._bake.find_ami.assert_called_once_with("c", "mhcphase1")
        self._bake.hc_option.assert_called_once_with(ANY, "phase1_ami_name")

    def test_get_phase1_ami_id_raises(self):
        '''Test that get_phase1_ami_id raises AMIError if find_ami returns None'''
        self._bake.find_ami = Mock(return_value=None)
        self.assertRaises(AMIError, self._bake._get_phase1_ami_id, "mhcntp")

    def test_list_amis(self):
        '''Test that list amis can be called without filter successfully'''
        self.assertEqual(self._bake.list_amis(), self._amis)

    def test_list_amis_by_product_line(self):
        '''Test that list amis can filter by product line successfully'''
        self.assertEqual(
            self._bake.list_amis(product_line="astro"), [
                self._amis_by_name["mhcfoo 1"],
                self._amis_by_name["mhcfoo 4"]])

    def test_list_amis_by_stage(self):
        '''Test that list amis can filter by stage successfully'''
        self.assertEqual(self._bake.list_amis(stage="failed"),
                         [self._amis_by_name["mhcfoo 5"]])

    def test_list_amis_by_productline_and_stage(self):
        '''Test that list amis can filter by productline and stage successfully'''
        self.assertEqual(self._bake.list_amis(stage="tested", product_line="someone_else"),
                         [self._amis_by_name["mhcbar 1"]])
