"""
Tests of disco_acm
"""
from unittest import TestCase
from mock import MagicMock

from disco_aws_automation import DiscoACM
from disco_aws_automation.disco_acm import (
    CERT_SUMMARY_LIST_KEY,
    CERT_ARN_KEY,
    DOMAIN_NAME_KEY
)

TEST_DOMAIN_NAME = 'test.example.com'
TEST_DEEP_DOMAIN_NAME = 'a.deeper.test.example.com'
TEST_WILDCARD_DOMAIN_NAME = '*.example.com'
TEST_CERTIFICATE_ARN_ACM_EXACT = "arn:aws:acm::123:exact"
TEST_CERTIFICATE_ARN_ACM_WILDCARD = "arn:aws:acm::123:wildcard"

TEST_CERT = {CERT_ARN_KEY: TEST_CERTIFICATE_ARN_ACM_EXACT, DOMAIN_NAME_KEY: TEST_DOMAIN_NAME}
TEST_WILDCARD_CERT = {CERT_ARN_KEY: TEST_CERTIFICATE_ARN_ACM_WILDCARD,
                      DOMAIN_NAME_KEY: TEST_WILDCARD_DOMAIN_NAME}


class DiscoACMTests(TestCase):
    '''Test disco_acm.py'''

    def setUp(self):
        self._acm = MagicMock()
        self.disco_acm = DiscoACM(self._acm)

    def test_get_certificate_arn_exact_match(self):
        """
        exact match between the host and cert work
        e.g. a.b.c matches a.b.c
        """
        self._acm.list_certificates.return_value = {CERT_SUMMARY_LIST_KEY: [TEST_CERT]}
        self.assertEqual(TEST_CERTIFICATE_ARN_ACM_EXACT,
                         self.disco_acm.get_certificate_arn(TEST_DOMAIN_NAME),
                         'Exact matching of host domain name to cert domain needs to be fixed.')

    def test_get_certificate_arn_wildcard_match(self):
        """
        wildcard match between the host and cert work
        e.g. a.b.c matches *.b.c
        """
        self._acm.list_certificates.return_value = {CERT_SUMMARY_LIST_KEY: [TEST_WILDCARD_CERT]}
        self.assertEqual(TEST_CERTIFICATE_ARN_ACM_WILDCARD,
                         self.disco_acm.get_certificate_arn(TEST_DOMAIN_NAME),
                         'Exact matching of host domain name to cert domain needs to be fixed.')

    def test_get_certificate_arn_empty(self):
        """
        empty string should not should NOT return a cert
        e.g. '' does not match a.b.c or *.b.c
        """
        self._acm.list_certificates.return_value = {CERT_SUMMARY_LIST_KEY: [TEST_CERT, TEST_WILDCARD_CERT]}
        self.assertFalse(self.disco_acm.get_certificate_arn(''),
                         'An empty string should not match certs.')

    def test_get_certificate_arn_no_hostname(self):
        """
        dns names beginning with . should NOT return a cert
        e.g. .b.c does not match a.b.c or *.b.c
        """
        self._acm.list_certificates.return_value = {CERT_SUMMARY_LIST_KEY: [TEST_CERT, TEST_WILDCARD_CERT]}
        self.assertFalse(self.disco_acm.get_certificate_arn('.example.com'),
                         'A missing host name should not match cert domains.')

    def test_get_certificate_arn_no_match(self):
        """
        host that does not match cert domains should NOT return a cert
        e.f.g.h does not match a.b.c or *.b.c
        """
        self._acm.list_certificates.return_value = {CERT_SUMMARY_LIST_KEY: [TEST_CERT, TEST_WILDCARD_CERT]}
        self.assertFalse(self.disco_acm.get_certificate_arn('non.existent.cert.domain'),
                         'Matching of host domain name to cert domain is generating false positives.')

    def test_get_certificate_arn_substring(self):
        """
        host that is a only a substring of a domain should NOT return a cert
        a.b does not match a.b.c or *.b.c
        """
        self._acm.list_certificates.return_value = {CERT_SUMMARY_LIST_KEY: [TEST_CERT, TEST_WILDCARD_CERT]}
        self.assertFalse(self.disco_acm.get_certificate_arn('test.example'),
                         'a.b should not match a.b.c or *.b.c.')

    def test_get_cert_arn_match_most_specific(self):
        """
        test both orderings of exact and wildcard matching cert domains
        to ensure the host domain matches the most specific cert domain in both cases
        a.b.c will match a.b.c in preference to *.b.c
        """
        self._acm.list_certificates.return_value = {CERT_SUMMARY_LIST_KEY: [TEST_CERT, TEST_WILDCARD_CERT]}
        self.assertEqual(TEST_CERTIFICATE_ARN_ACM_EXACT,
                         self.disco_acm.get_certificate_arn(TEST_DOMAIN_NAME),
                         'Failed to match most specific cert domain.')
        self._acm.list_certificates.return_value = {CERT_SUMMARY_LIST_KEY: [TEST_WILDCARD_CERT, TEST_CERT]}
        self.assertEqual(TEST_CERTIFICATE_ARN_ACM_EXACT,
                         self.disco_acm.get_certificate_arn(TEST_DOMAIN_NAME),
                         'Failed to match most specific cert domain.')
