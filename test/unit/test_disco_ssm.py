"""Tests of disco_ssm"""
import copy
from unittest import TestCase
from mock import MagicMock, patch
import json

from botocore.exceptions import ClientError

from disco_aws_automation import DiscoSSM
from disco_aws_automation.disco_ssm import SSM_DOCUMENTS_DIR

from test.helpers.patch_disco_aws import (get_mock_config,
                                          TEST_ENV_NAME)

MOCK_AWS_CONFIG_DEFINITION = {
    "disco_aws": {
        "default_environment": TEST_ENV_NAME,
    }
}
MOCK_RANDOM_DOCUMENTS = [
    {
        'Name': 'random_document_1',
        'Owner': 'mock_owner',
        'PlatformTypes': ['Linux']
    },
    {
        'Name': 'random_document_2',
        'Owner': 'mock_owner',
        'PlatformTypes': ['Linux']
    }
]
MOCK_ASIAQ_DOCUMENTS = [
    {
        'Name': 'asiaq-ssm_document_1',
        'Owner': 'mock_owner',
        'PlatformTypes': ['Linux']
    },
    {
        'Name': 'asiaq-ssm_document_2',
        'Owner': 'mock_owner',
        'PlatformTypes': ['Linux']
    }
]
MOCK_ASIAQ_DOCUMENT_CONTENTS = {
    'asiaq-ssm_document_1': '{"field1": "value1"}',
    'asiaq-ssm_document_2': '{"field1": "value1"}',
}
MOCK_ASIAQ_DOCUMENT_FILE_CONTENTS = {
    SSM_DOCUMENTS_DIR + '/ssm_document_1.ssm': MOCK_ASIAQ_DOCUMENT_CONTENTS['asiaq-ssm_document_1'],
    SSM_DOCUMENTS_DIR + '/ssm_document_2.ssm': MOCK_ASIAQ_DOCUMENT_CONTENTS['asiaq-ssm_document_2'],
}


def mock_boto3_client(arg):
    """ mock method for boto3.client() """
    if arg != "ssm":
        raise Exception("Mock %s client not implemented.", arg)

    mock_asiaq_documents = copy.copy(MOCK_ASIAQ_DOCUMENTS)
    mock_asiaq_document_contents = copy.copy(MOCK_ASIAQ_DOCUMENT_CONTENTS)

    def mock_list_documents():
        return {
            'DocumentIdentifiers': mock_asiaq_documents + MOCK_RANDOM_DOCUMENTS,
            'NextToken': ''
        }

    def mock_get_document(Name):
        if Name not in mock_asiaq_document_contents:
            raise ClientError({'Error': {'Code': 'Mock_code', 'Message': 'mock message'}},
                              'GetDocument')

        return {'Name': Name,
                'Content': mock_asiaq_document_contents[Name]}

    def mock_create_document(Content, Name):
        mock_asiaq_documents.append({'Name': Name,
                                     'Owner': 'mock_owner',
                                     'PlatformTypes': ['Linux']})
        mock_asiaq_document_contents[Name] = Content

    mock_ssm = MagicMock()
    mock_ssm.list_documents.side_effect = mock_list_documents
    mock_ssm.get_document.side_effect = mock_get_document
    mock_ssm.create_document.side_effect = mock_create_document

    return mock_ssm


def create_mock_open(content_dict):
    """
    Creates a mock open method that returns the file content based
    on the dict being passed in
    """
    def mock_open(file_name, mode):
        if file_name not in content_dict:
            raise RuntimeError("File name ({0}) not in content dict.".format(file_name))

        if mode != 'r':
            raise RuntimeError("SSM documents should only be opened by asiaq in read mode.")

        mock_file = MagicMock(spec=file)
        mock_file.__enter__.return_value = mock_file
        mock_file.read.return_value = content_dict[file_name]
        return mock_file

    return mock_open


def _standardize_json_str(json_str):
        return json.dumps(json.loads(json_str), indent=4)


class DiscoSSMTests(TestCase):
    """Test DiscoSSM"""

    def setUp(self):
        
        config_aws = get_mock_config(MOCK_AWS_CONFIG_DEFINITION)
        self._ssm = DiscoSSM(environment_name=TEST_ENV_NAME,
                             config_aws=config_aws)

    @patch('boto3.client', mock_boto3_client)
    def test_get_all_documents(self):
        """Verify that get_all_documents() works"""

        # Calling the method under test
        documents = self._ssm.get_all_documents()

        # Make sure the documents returned contain only the asiaq-managed ones
        self.assertEquals(documents, MOCK_ASIAQ_DOCUMENTS)

    @patch('boto3.client', mock_boto3_client)
    def test_get_document_content(self):
        """Verify content of a document is correctly retrieved"""

        # Calling the method under test
        doc_content_1 = self._ssm.get_document_content('asiaq-ssm_document_1')
        doc_content_2 = self._ssm.get_document_content('asiaq-ssm_document_2')

        # Verify result
        self.assertEquals(doc_content_1, MOCK_ASIAQ_DOCUMENT_CONTENTS['asiaq-ssm_document_1'])
        self.assertEquals(doc_content_2, MOCK_ASIAQ_DOCUMENT_CONTENTS['asiaq-ssm_document_2'])

    @patch('boto3.client', mock_boto3_client)
    def test_get_document_content_invalid_doc_name(self):
        """Verify correct error is thrown when doc_name is invalid"""

        # Calling the method under test
        self.assertRaises(Exception, self._ssm.get_document_content, doc_name='random_doc')

    @patch('boto3.client', mock_boto3_client)
    def test_get_document_content_doc_name_not_found(self):
        """Verify no content is returned when doc_name is not found"""

        # Calling the method under test
        doc_content = self._ssm.get_document_content('asiaq-random_doc')

        # Verifying result
        self.assertEquals(doc_content, None)

    @patch('boto3.client', mock_boto3_client)
    @patch('os.listdir')
    @patch('disco_aws_automation.disco_ssm.open')
    def test_update_create_docs(self, mock_open, mock_os_listdir):
        """Verify that creating new documents in the update() method works"""
        # Setting up test
        mock_os_listdir.return_value = ['ssm_document_1.ssm', 'ssm_document_2.ssm',
                                        'ssm_document_3.ssm',
                                        'random_file1.txt', 'random_file2.jpg']

        mock_doc_content = '{"random_field": "random_value"}'
        mock_file_contents = copy.copy(MOCK_ASIAQ_DOCUMENT_FILE_CONTENTS)
        mock_file_contents[SSM_DOCUMENTS_DIR + '/ssm_document_3.ssm'] = mock_doc_content
        mock_open.side_effect = create_mock_open(mock_file_contents)

        # Calling the method under test
        self._ssm.update()

        # Verify document is created successfully
        self.assertEquals(_standardize_json_str(mock_doc_content),
                          _standardize_json_str(
                            self._ssm.get_document_content('asiaq-ssm_document_3')))
