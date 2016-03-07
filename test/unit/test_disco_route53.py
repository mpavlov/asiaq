"""Tests of disco_route53"""
from unittest import TestCase

from boto.route53.record import Record
from moto import mock_route53, mock_sns

from disco_aws_automation import DiscoRoute53

TEST_DOMAIN = 'example.com.'
TEST_DOMAIN2 = 'foo.com.'
TEST_RECORD_NAME = 'subdomain.example.com.'
TEST_RECORD_NAME2 = 'subdomain.foo.com.'
TEST_RECORD_TYPE = 'CNAME'
TEST_RECORD_VALUE = 'some.value'


def _create_mock_zone_and_records(route53):
    route53.create_hosted_zone(TEST_DOMAIN)
    route53.create_hosted_zone(TEST_DOMAIN2)
    example_com = route53.get_zone(TEST_DOMAIN)
    test_com = route53.get_zone(TEST_DOMAIN2)

    record_sets = route53.get_all_rrsets(example_com.id)

    record = Record(TEST_RECORD_NAME, TEST_RECORD_TYPE)
    record.add_value(TEST_RECORD_VALUE)

    record_sets.add_change_record('CREATE', record)
    record_sets.commit()

    record_sets = route53.get_all_rrsets(test_com.id)

    record = Record(TEST_RECORD_NAME2, TEST_RECORD_TYPE)
    record.add_value(TEST_RECORD_VALUE)

    record_sets.add_change_record('CREATE', record)
    record_sets.commit()


class DiscoRoute53Tests(TestCase):
    """Test DiscoRoute53"""

    @mock_sns
    @mock_route53
    def test_list_zones(self):
        """Test listing the available hosted zones"""
        disco_route53 = DiscoRoute53()

        _create_mock_zone_and_records(disco_route53.route53)

        zones = disco_route53.list_zones()

        self.assertEquals(len(zones), 2)
        self.assertEquals(zones[0].name, TEST_DOMAIN)
        self.assertEquals(zones[1].name, TEST_DOMAIN2)

    @mock_sns
    @mock_route53
    def test_list_records(self):
        """Test listing records for a hosted zone"""
        disco_route53 = DiscoRoute53()

        _create_mock_zone_and_records(disco_route53.route53)

        records = disco_route53.list_records(TEST_DOMAIN)

        self.assertEquals(len(records), 1)
        self.assertEquals(records[0].name, TEST_RECORD_NAME)

    @mock_sns
    @mock_route53
    def test_delete_records_by_value(self):
        """Test deleting records by value"""
        disco_route53 = DiscoRoute53()

        _create_mock_zone_and_records(disco_route53.route53)

        disco_route53.delete_records_by_value(TEST_RECORD_TYPE, TEST_RECORD_VALUE)

        zone = disco_route53.route53.get_zones()[0]
        self.assertEquals(len(disco_route53.route53.get_all_rrsets(zone.id)), 0)

    @mock_sns
    @mock_route53
    def test_get_records_by_value(self):
        """Test getting records by value"""
        disco_route53 = DiscoRoute53()

        _create_mock_zone_and_records(disco_route53.route53)

        actual = disco_route53.get_records_by_value(TEST_RECORD_TYPE, TEST_RECORD_VALUE)
        expected = [{
            'zone_name': TEST_DOMAIN,
            'record_name': TEST_RECORD_NAME
        }, {
            'zone_name': TEST_DOMAIN2,
            'record_name': TEST_RECORD_NAME2
        }]

        self.assertEquals(actual, expected)
