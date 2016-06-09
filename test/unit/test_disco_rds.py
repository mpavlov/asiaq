"""
Tests of disco_rds
"""
import unittest

from mock import MagicMock, patch

from disco_aws_automation.disco_rds import DiscoRDS
from disco_aws_automation.exceptions import RDSEnvironmentError
from test.helpers.patch_disco_aws import get_mock_config

TEST_ENV_NAME = 'unittestenv'
TEST_VPC_ID = 'vpc-56e10e3d'  # the hard coded VPC Id that moto will always return

MOCK_SG_GROUP_ID = 'mock_sg_group_id'


def _get_vpc_mock():
    """Nastily copied from test_disco_elb"""
    vpc_mock = MagicMock()
    vpc_mock.environment_name = TEST_ENV_NAME
    vpc_mock.vpc = MagicMock()
    vpc_mock.vpc.id = TEST_VPC_ID
    return vpc_mock


def _get_bucket_mock():
    def _get_key_mock(key_name):
        if key_name == 'rds/db-name/master_user_password':
            return 'database_name_key'
        elif key_name == 'rds/unittestenv-db-id/master_user_password':
            return 'database-id-key'
        else:
            raise KeyError("Key not found")

    def _key_exists_mock(key_name):
        return key_name in ['rds/db-name/master_user_password', 'rds/unittestenv-db-id/master_user_password']

    bucket = MagicMock()
    bucket.get_key.side_effect = _get_key_mock
    bucket.key_exists.side_effect = _key_exists_mock

    return bucket


def _get_vpc_sg_rules_mock():
    vpc_sg_rules_mock = MagicMock()
    vpc_sg_rules_mock.get_all_security_groups_for_vpc.return_value = [{
        'GroupId': MOCK_SG_GROUP_ID,
        'Tags': [{'Key': 'meta_network', 'Value': 'intranet'}]}]

    return vpc_sg_rules_mock


class DiscoRDSTests(unittest.TestCase):
    """Test DiscoRDS class"""

    def setUp(self):
        with patch('disco_aws_automation.disco_rds.DiscoVPCSecurityGroupRules',
                   return_value=_get_vpc_sg_rules_mock()):

            self.rds = DiscoRDS(_get_vpc_mock())
            self.rds.client = MagicMock()
            self.rds.config_rds = get_mock_config({
                'some-env-db-name': {
                    'engine': 'oracle',
                    'allocated_storage': '100',
                    'db_instance_class': 'db.m4.2xlarge',
                    'engine_version': '12.1.0.2.v2',
                    'master_username': 'foo'

                }
            })
            self.rds.domain_name = 'example.com'

    def test_get_db_parameter_group_family(self):
        """Tests that get_db_parameter_group_family handles all the expected cases"""
        self.assertEquals("postgresql9.3", self.rds.get_db_parameter_group_family("postgresql", "9.3.1"))
        self.assertEquals("oracle-se2-12.1",
                          self.rds.get_db_parameter_group_family("oracle-se2", "12.1.0.2.v2"))
        self.assertEquals("mysql123.5", self.rds.get_db_parameter_group_family("MySQL", "123.5"))

    # pylint: disable=unused-argument
    @patch('disco_aws_automation.disco_rds.DiscoS3Bucket', return_value=_get_bucket_mock())
    def test_get_master_password(self, bucket_mock):
        """test getting the master password for an instance using either the db name or id as the s3 key"""
        self.assertEquals('database_name_key', self.rds.get_master_password(TEST_ENV_NAME, 'db-name'))
        self.assertEquals('database-id-key', self.rds.get_master_password(TEST_ENV_NAME, 'db-id'))

    # pylint: disable=unused-argument
    @patch('disco_aws_automation.disco_rds.DiscoS3Bucket', return_value=_get_bucket_mock())
    def test_clone_existing_db(self, bucket_mock):
        """test that cloning throws an error when the destination db already exists"""
        self.rds.client.describe_db_snapshots.return_value = {
            'DBInstances': [{
                'DBInstanceIdentifier': 'unittestenv-db-name'
            }]
        }

        with(self.assertRaises(RDSEnvironmentError)):
            self.rds.clone('some-env', 'db-name')

    # pylint: disable=unused-argument
    @patch('disco_aws_automation.disco_rds.DiscoRoute53')
    @patch('disco_aws_automation.disco_rds.DiscoS3Bucket', return_value=_get_bucket_mock())
    def test_clone(self, bucket_mock, r53_mock):
        """test cloning a database"""
        self.rds._get_db_instance = MagicMock(return_value=None)
        self.rds.client.describe_db_snapshots.return_value = {
            'DBSnapshots': [{
                'DBSnapshotIdentifier': 'foo-snapshot'
            }]
        }
        self.rds.client.describe_db_instances.return_value = {
            'DBInstances': [{
                'Endpoint': {
                    'Address': 'foo.example.com'
                }
            }]
        }

        self.rds.clone('some-env', 'db-name')

        self.rds.client.restore_db_instance_from_db_snapshot.assert_called_once_with(
            AutoMinorVersionUpgrade=True,
            DBInstanceClass='db.m4.2xlarge',
            DBInstanceIdentifier='unittestenv-db-name',
            DBSnapshotIdentifier='foo-snapshot',
            DBSubnetGroupName='unittestenv-db-name',
            Engine='oracle',
            Iops=0,
            LicenseModel='bring-your-own-license',
            MultiAZ=True,
            Port=1521,
            PubliclyAccessible=False)

        self.rds.client.create_db_parameter_group.assert_called_once_with(
            DBParameterGroupName='unittestenv-db-name',
            DBParameterGroupFamily='oracle12.1',
            Description='Custom params-unittestenv-db-name')

        r53_mock.return_value.create_record.assert_called_once_with('example.com',
                                                                    'unittestenv-db-name.example.com.',
                                                                    'CNAME',
                                                                    'foo.example.com')

    def test_get_rds_security_group_id(self):
        """ Verify security group ID is retrieved correctly """
        sg_group_id = self.rds.get_rds_security_group_id()

        self.assertEqual(MOCK_SG_GROUP_ID, sg_group_id)
