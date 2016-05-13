"""Tests of disco_elb"""
from unittest import TestCase
from mock import MagicMock
from moto import mock_elb
from disco_aws_automation import DiscoELB

TEST_ENV_NAME = 'unittestenv'
TEST_HOSTCLASS = 'mhcunit'
TEST_VPC_ID = 'vpc-56e10e3d'  # the hard coded VPC Id that moto will always return
TEST_DOMAIN_NAME = 'test.example.com'
TEST_CERTIFICATE_ARN_ACM = "arn:aws:acm::123:blah"
TEST_CERTIFICATE_ARN_IAM = "arn:aws:acm::123:blah"


def _get_vpc_mock():
    vpc_mock = MagicMock()
    vpc_mock.environment_name = TEST_ENV_NAME
    vpc_mock.vpc = MagicMock()
    vpc_mock.vpc.id = TEST_VPC_ID
    return vpc_mock


class DiscoELBTests(TestCase):
    """Test DiscoELB"""

    def setUp(self):
        self.route53 = MagicMock()
        self.acm = MagicMock()
        self.iam = MagicMock()
        self.disco_elb = DiscoELB(_get_vpc_mock(), route53=self.route53, acm=self.acm, iam=self.iam)
        self.acm.get_certificate_arn.return_value = TEST_CERTIFICATE_ARN_ACM
        self.iam.get_certificate_arn.return_value = TEST_CERTIFICATE_ARN_IAM

    # pylint: disable=too-many-arguments
    def _create_elb(self, hostclass=None, public=False, tls=False,
                    instance_protocol='HTTP', instance_port=80,
                    elb_protocol='HTTP', elb_port=80,
                    idle_timeout=None, connection_draining_timeout=None,
                    sticky_app_cookie=None):
        return self.disco_elb.get_or_create_elb(
            hostclass=hostclass or TEST_HOSTCLASS,
            security_groups=['sec-1'],
            subnets=['sub-1'],
            hosted_zone_name=TEST_DOMAIN_NAME,
            health_check_url="/" if instance_protocol.upper() in ('HTTP', 'HTTPS') else "",
            instance_protocol=instance_protocol,
            instance_port=instance_port,
            elb_protocol="HTTPS" if tls else elb_protocol,
            elb_port=443 if tls else elb_port,
            elb_public=public,
            sticky_app_cookie=sticky_app_cookie,
            idle_timeout=idle_timeout,
            connection_draining_timeout=connection_draining_timeout)

    @mock_elb
    def test_get_certificate_arn_prefers_acm(self):
        '''get_certificate_arn() prefers an ACM provided certificate'''
        self.assertEqual(self.disco_elb.get_certificate_arn("dummy"), TEST_CERTIFICATE_ARN_ACM)

    @mock_elb
    def test_get_certificate_arn_fallback_to_iam(self):
        '''get_certificate_arn() uses an IAM certificate if no ACM cert available'''
        self.acm.get_certificate_arn.return_value = None
        self.assertEqual(self.disco_elb.get_certificate_arn("dummy"), TEST_CERTIFICATE_ARN_IAM)

    @mock_elb
    def test_get_cname(self):
        '''Make sure get_cname returns what we expect'''
        self.assertEqual(self.disco_elb.get_cname(TEST_HOSTCLASS, TEST_DOMAIN_NAME),
                         "mhcunit-unittestenv.test.example.com")

    @mock_elb
    def test_get_elb_with_create(self):
        """Test creating a ELB"""
        self._create_elb()
        self.assertEquals(
            len(self.disco_elb.elb_client.describe_load_balancers()['LoadBalancerDescriptions']), 1)

    @mock_elb
    def test_get_elb_with_update(self):
        """Updating an ELB doesn't add create a new ELB"""
        self._create_elb()
        self._create_elb()
        self.assertEquals(
            len(self.disco_elb.elb_client.describe_load_balancers()['LoadBalancerDescriptions']), 1)

    @mock_elb
    def test_get_elb_internal(self):
        """Test creation an internal private ELB"""
        elb_client = self.disco_elb.elb_client
        elb_client.create_load_balancer = MagicMock(wraps=elb_client.create_load_balancer)
        self._create_elb()
        self.disco_elb.elb_client.create_load_balancer.assert_called_once_with(
            LoadBalancerName=DiscoELB.get_elb_name('unittestenv', 'mhcunit'),
            Listeners=[{
                'Protocol': 'HTTP',
                'LoadBalancerPort': 80,
                'InstanceProtocol': 'HTTP',
                'InstancePort': 80
            }],
            Subnets=['sub-1'],
            SecurityGroups=['sec-1'],
            Scheme='internal',
            Tags=[{
                "Key": "elb_name",
                "Value": DiscoELB.get_elb_name_for_humans('unittestenv', 'mhcunit')
            }])

    @mock_elb
    def test_get_elb_internal_no_tls(self):
        """Test creation an internal private ELB"""
        self.acm.get_certificate_arn.return_value = None
        self.iam.get_certificate_arn.return_value = None
        elb_client = self.disco_elb.elb_client
        elb_client.create_load_balancer = MagicMock(wraps=elb_client.create_load_balancer)
        self._create_elb()
        elb_client.create_load_balancer.assert_called_once_with(
            LoadBalancerName=DiscoELB.get_elb_name('unittestenv', 'mhcunit'),
            Listeners=[{
                'Protocol': 'HTTP',
                'LoadBalancerPort': 80,
                'InstanceProtocol': 'HTTP',
                'InstancePort': 80
            }],
            Subnets=['sub-1'],
            SecurityGroups=['sec-1'],
            Scheme='internal',
            Tags=[{
                "Key": "elb_name",
                "Value": DiscoELB.get_elb_name_for_humans('unittestenv', 'mhcunit')
            }])

    @mock_elb
    def test_get_elb_external(self):
        """Test creation a publically accessible ELB"""
        elb_client = self.disco_elb.elb_client
        elb_client.create_load_balancer = MagicMock(wraps=elb_client.create_load_balancer)
        self._create_elb(public=True)
        elb_client.create_load_balancer.assert_called_once_with(
            LoadBalancerName=DiscoELB.get_elb_name('unittestenv', 'mhcunit'),
            Listeners=[{
                'Protocol': 'HTTP',
                'LoadBalancerPort': 80,
                'InstanceProtocol': 'HTTP',
                'InstancePort': 80
            }],
            Subnets=['sub-1'],
            SecurityGroups=['sec-1'],
            Tags=[{
                "Key": "elb_name",
                "Value": DiscoELB.get_elb_name_for_humans('unittestenv', 'mhcunit')
            }])

    @mock_elb
    def test_get_elb_with_tls(self):
        """Test creation an ELB with TLS"""
        elb_client = self.disco_elb.elb_client
        elb_client.create_load_balancer = MagicMock(wraps=elb_client.create_load_balancer)
        self._create_elb(tls=True)
        elb_client.create_load_balancer.assert_called_once_with(
            LoadBalancerName=DiscoELB.get_elb_name('unittestenv', 'mhcunit'),
            Listeners=[{
                'Protocol': 'HTTPS',
                'LoadBalancerPort': 443,
                'InstanceProtocol': 'HTTP',
                'InstancePort': 80,
                'SSLCertificateId': TEST_CERTIFICATE_ARN_ACM
            }],
            Subnets=['sub-1'],
            SecurityGroups=['sec-1'],
            Scheme='internal',
            Tags=[{
                "Key": "elb_name",
                "Value": DiscoELB.get_elb_name_for_humans('unittestenv', 'mhcunit')
            }])

    @mock_elb
    def test_get_elb_with_tcp(self):
        """Test creation an ELB with TCP"""
        elb_client = self.disco_elb.elb_client
        elb_client.create_load_balancer = MagicMock(wraps=elb_client.create_load_balancer)
        self._create_elb(instance_protocol='TCP', instance_port=25,
                         elb_protocol='TCP', elb_port=25)
        elb_client.create_load_balancer.assert_called_once_with(
            LoadBalancerName=DiscoELB.get_elb_name('unittestenv', 'mhcunit'),
            Listeners=[{
                'Protocol': 'TCP',
                'LoadBalancerPort': 25,
                'InstanceProtocol': 'TCP',
                'InstancePort': 25
            }],
            Subnets=['sub-1'],
            SecurityGroups=['sec-1'],
            Scheme='internal',
            Tags=[{
                "Key": "elb_name",
                "Value": DiscoELB.get_elb_name_for_humans('unittestenv', 'mhcunit')
            }])

    @mock_elb
    def test_get_elb_with_idle_timeout(self):
        """Test creating an ELB with an idle timeout"""
        client = self.disco_elb.elb_client
        client.modify_load_balancer_attributes = MagicMock(wraps=client.modify_load_balancer_attributes)

        self._create_elb(idle_timeout=100)

        client.modify_load_balancer_attributes.assert_called_once_with(
            LoadBalancerName=DiscoELB.get_elb_name('unittestenv', 'mhcunit'),
            LoadBalancerAttributes={'ConnectionDraining': {'Enabled': False, 'Timeout': 0},
                                    'ConnectionSettings': {'IdleTimeout': 100}}
        )

    @mock_elb
    def test_get_elb_with_connection_draining(self):
        """Test creating ELB with connection draining"""
        client = self.disco_elb.elb_client
        client.modify_load_balancer_attributes = MagicMock(wraps=client.modify_load_balancer_attributes)

        self._create_elb(connection_draining_timeout=100)

        client.modify_load_balancer_attributes.assert_called_once_with(
            LoadBalancerName=DiscoELB.get_elb_name('unittestenv', 'mhcunit'),
            LoadBalancerAttributes={'ConnectionDraining': {'Enabled': True, 'Timeout': 100}}
        )

    @mock_elb
    def test_delete_elb(self):
        """Test deleting an ELB"""
        self._create_elb()
        self.disco_elb.delete_elb(TEST_HOSTCLASS)
        load_balancers = self.disco_elb.elb_client.describe_load_balancers()['LoadBalancerDescriptions']
        self.assertEquals(len(load_balancers), 0)

    @mock_elb
    def test_get_existing_elb(self):
        """Test get_elb for a hostclass"""
        self._create_elb()
        self.assertIsNotNone(self.disco_elb.get_elb(TEST_HOSTCLASS))

    @mock_elb
    def test_list(self):
        """Test getting the list of ELBs"""
        self._create_elb(hostclass='mhcbar')
        self._create_elb(hostclass='mhcfoo')
        self.assertEquals(len(self.disco_elb.list()), 2)

    @mock_elb
    def test_elb_delete(self):
        """Test deletion of ELBs"""
        self._create_elb(hostclass='mhcbar')
        self.disco_elb.delete_elb(hostclass='mhcbar')
        self.assertEquals(len(self.disco_elb.list()), 0)

    @mock_elb
    def test_destroy_all_elbs(self):
        """Test deletion of all ELBs"""
        self._create_elb(hostclass='mhcbar')
        self._create_elb(hostclass='mhcfoo')
        self.disco_elb.destroy_all_elbs()
        self.assertEquals(len(self.disco_elb.list()), 0)
