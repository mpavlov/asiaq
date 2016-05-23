"""
Tests of disco_acm
"""
from unittest import TestCase
from mock import MagicMock

from disco_aws_automation import DiscoACM
from disco_aws_automation.disco_acm import (
    CERT_ARN_KEY,
    DOMAIN_NAME_KEY
)

TEST_DOMAIN_NAME = 'test.example.com'
TEST_WILDCARD_DOMAIN_NAME = '*.example.com'
TEST_CERTIFICATE_ARN_ACM = "arn:aws:acm::123:blah"

TEST_CERT = {CERT_ARN_KEY: TEST_CERTIFICATE_ARN_ACM, DOMAIN_NAME_KEY: TEST_DOMAIN_NAME}
TEST_WILDCARD_CERT = {CERT_ARN_KEY: TEST_CERTIFICATE_ARN_ACM, DOMAIN_NAME_KEY: TEST_WILDCARD_DOMAIN_NAME}

class DiscoACMTests(TestCase):
    '''Test disco_acm.py'''

    def setUp(self):
        self._acm = MagicMock()
        self.disco_acm = DiscoACM(self._acm)

    def test_get_certificate_arn_exact_match(self):
        """exact match between the host and cert work"""
        self._acm.list_certificates.return_value = [TEST_CERT]
        self.assertTrue(self.disco_acm.get_certificate_arn(TEST_DOMAIN_NAME))

    def test_get_certificate_arn_exact_match_wildcard(self):
        """exact match between the host and wildcard cert do not work"""
        self._acm.list_certificates.return_value = [TEST_WILDCARD_CERT]
        self.assertFalse(self.disco_acm.get_certificate_arn(TEST_WILDCARD_DOMAIN_NAME))
