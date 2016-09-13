"""Tests of disco_ssm"""
import copy
import json
from unittest import TestCase
from mock import MagicMock, patch, call

from botocore.exceptions import ClientError

from disco_aws_automation import DiscoSSM
from disco_aws_automation.disco_ssm import SSM_DOCUMENTS_DIR

from test.helpers.patch_disco_aws import (get_mock_config,
                                          TEST_ENV_NAME)

MOCK_AWS_CONFIG_DEFINITION = {
    'disco_aws': {
        'default_environment': TEST_ENV_NAME,
    }}
MOCK_AWS_DOCUMENTS = [
    {
        'Name': 'AWS-document_1',
        'Owner': 'mock_owner',
        'PlatformTypes': ['Linux']
    },
    {
        'Name': 'AWS-document_2',
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
    'asiaq-ssm_document_2': '{"field2": "value2"}',
}
MOCK_ASIAQ_DOCUMENT_FILE_CONTENTS = {
    SSM_DOCUMENTS_DIR + '/asiaq-ssm_document_1.ssm': MOCK_ASIAQ_DOCUMENT_CONTENTS['asiaq-ssm_document_1'],
    SSM_DOCUMENTS_DIR + '/asiaq-ssm_document_2.ssm': MOCK_ASIAQ_DOCUMENT_CONTENTS['asiaq-ssm_document_2'],
}
MOCK_NEXT_TOKEN = "abcdefgABCDEFG"


# pylint: disable=invalid-name
def mock_boto3_client(arg):
    """ mock method for boto3.client() """
    if arg != "ssm":
        raise Exception("Mock %s client not implemented.", arg)

    mock_asiaq_documents = copy.copy(MOCK_ASIAQ_DOCUMENTS)
    mock_asiaq_document_contents = copy.copy(MOCK_ASIAQ_DOCUMENT_CONTENTS)
    wait_flags = {'delete': True, 'create': True}

    def _mock_list_documents(NextToken=''):
        all_documents = MOCK_AWS_DOCUMENTS + mock_asiaq_documents
        if NextToken == '':
            return {
                'DocumentIdentifiers': all_documents[:len(all_documents) / 2],
                'NextToken': MOCK_NEXT_TOKEN
            }
        elif NextToken == MOCK_NEXT_TOKEN:
            return {
                'DocumentIdentifiers': all_documents[len(all_documents) / 2:],
                'NextToken': ''
            }
        else:
            raise RuntimeError("Invalid NextToken: {0}".format(NextToken))

    def _mock_get_document(Name):
        if Name not in mock_asiaq_document_contents:
            raise ClientError({'Error': {'Code': 'Mock_code', 'Message': 'mock message'}},
                              'GetDocument')

        return {'Name': Name,
                'Content': mock_asiaq_document_contents[Name]}

    def _mock_create_document(Content, Name):
        mock_asiaq_documents.append({'Name': Name,
                                     'Owner': 'mock_owner',
                                     'PlatformTypes': ['Linux']})
        mock_asiaq_document_contents[Name] = Content

    def _mock_delete_document(Name):
        doc_to_delete = [document for document in mock_asiaq_documents
                         if document['Name'] == Name]
        if doc_to_delete:
            mock_asiaq_documents.remove(doc_to_delete[0])
        mock_asiaq_document_contents.pop(Name, None)

    def _mock_describe_document(Name):
        # Using two wait flags to simulate that AWS is taking time to delete and
        # create documents
        if Name not in mock_asiaq_document_contents:
            if wait_flags['delete']:
                wait_flags['delete'] = False
                return {'Document': {'Name': Name, 'Status': 'Active'}}
            else:
                wait_flags['delete'] = True
                raise ClientError({'Error': {'Code': 'Mock_code', 'Message': 'mock message'}},
                                  'DescribeDocument')
        else:
            if wait_flags['create']:
                wait_flags['create'] = False
                return {'Document': {'Name': Name, 'Status': 'Creating'}}
            else:
                wait_flags['create'] = True
                return {'Document': {'Name': Name, 'Status': 'Active'}}

    mock_ssm = MagicMock()
    mock_ssm.list_documents.side_effect = _mock_list_documents
    mock_ssm.get_document.side_effect = _mock_get_document
    mock_ssm.create_document.side_effect = _mock_create_document
    mock_ssm.delete_document.side_effect = _mock_delete_document
    mock_ssm.describe_document.side_effect = _mock_describe_document

    return mock_ssm


def create_mock_open(content_dict):
    """
    Creates a mock open method that returns the file content based
    on the dict being passed in
    """
    def _mock_open(file_name, mode):
        if file_name not in content_dict:
            raise RuntimeError("File name ({0}) not in content dict.".format(file_name))

        if mode != 'r':
            raise RuntimeError("SSM documents should only be opened by asiaq in read mode.")

        mock_file = MagicMock(spec=file)
        mock_file.__enter__.return_value = mock_file
        mock_file.read.return_value = content_dict[file_name]
        return mock_file

    return _mock_open


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

        # Begin verifications
        # Make sure the documents returned contain only the asiaq-managed ones
        self.assertEquals(documents, MOCK_ASIAQ_DOCUMENTS)

        expected_list_calls = [call(), call(NextToken=MOCK_NEXT_TOKEN)]
        self.assertEquals(expected_list_calls,
                          self._ssm.conn.list_documents.mock_calls)

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
    def test_get_document_invalid_doc_name(self):
        """Verify correct error is thrown when doc_name is invalid"""

        # Calling the method under test
        self.assertRaises(Exception, self._ssm.get_document_content, doc_name='AWS-doc')

    @patch('boto3.client', mock_boto3_client)
    def test_get_document_doc_name_not_found(self):
        """Verify no content is returned when doc_name is not found"""

        # Calling the method under test
        doc_content = self._ssm.get_document_content('asiaq-random_doc')

        # Verifying results
        self.assertEquals(doc_content, None)

    @patch('boto3.client', mock_boto3_client)
    @patch('os.listdir')
    @patch('disco_aws_automation.disco_ssm.open')
    def test_update_create_docs(self, mock_open, mock_os_listdir):
        """Verify that creating new documents in the update() method works"""
        # Setting up test
        mock_os_listdir.return_value = ['asiaq-ssm_document_1.ssm', 'asiaq-ssm_document_2.ssm',
                                        'asiaq-ssm_document_3.ssm', 'asiaq-ssm_document_4.ssm',
                                        'random_file1.txt', 'random_file2.jpg']

        mock_doc_content_1 = '{"random_field_1": "random_value_1"}'
        mock_doc_content_2 = '{"random_field_2": "random_value_2"}'
        mock_file_contents = copy.copy(MOCK_ASIAQ_DOCUMENT_FILE_CONTENTS)
        mock_file_contents[SSM_DOCUMENTS_DIR + '/asiaq-ssm_document_3.ssm'] = mock_doc_content_1
        mock_file_contents[SSM_DOCUMENTS_DIR + '/asiaq-ssm_document_4.ssm'] = mock_doc_content_2
        mock_open.side_effect = create_mock_open(mock_file_contents)

        # Calling the method under test
        self._ssm.update(wait=False)

        # Verify documents are created successfully
        self.assertEquals(_standardize_json_str(mock_doc_content_1),
                          _standardize_json_str(
                              self._ssm.get_document_content('asiaq-ssm_document_3')))
        self.assertEquals(_standardize_json_str(mock_doc_content_2),
                          _standardize_json_str(
                              self._ssm.get_document_content('asiaq-ssm_document_4')))

    @patch('boto3.client', mock_boto3_client)
    @patch('os.listdir')
    @patch('disco_aws_automation.disco_ssm.open')
    def test_update_delete_docs(self, mock_open, mock_os_listdir):
        """Verify that deleting documents in the update() method works"""
        # Setting up test
        mock_os_listdir.return_value = ['asiaq-ssm_document_2.ssm', 'random_file1.txt',
                                        'random_file2.jpg']
        mock_file_contents = copy.copy(MOCK_ASIAQ_DOCUMENT_FILE_CONTENTS)
        mock_file_contents.pop(SSM_DOCUMENTS_DIR + '/asiaq-ssm_document_1.ssm', None)
        mock_open.side_effect = create_mock_open(mock_file_contents)

        # Calling the method under test
        self._ssm.update(wait=False)

        # Verify only document_1 is deleted
        self.assertTrue(self._ssm.get_document_content('asiaq-ssm_document_1') is None)
        self.assertEquals(_standardize_json_str(MOCK_ASIAQ_DOCUMENT_CONTENTS['asiaq-ssm_document_2']),
                          _standardize_json_str(
                              self._ssm.get_document_content('asiaq-ssm_document_2')))

    @patch('boto3.client', mock_boto3_client)
    @patch('os.listdir')
    @patch('disco_aws_automation.disco_ssm.open')
    def test_update_modify_docs(self, mock_open, mock_os_listdir):
        """Verify that modifying documents in the update() method works"""
        # Setting up test
        mock_os_listdir.return_value = ['asiaq-ssm_document_1.ssm', 'asiaq-ssm_document_2.ssm',
                                        'random_file1.txt', 'random_file2.jpg']

        new_doc_1_content = '{"random_field_1": "random_value_1"}'
        mock_file_contents = copy.copy(MOCK_ASIAQ_DOCUMENT_FILE_CONTENTS)
        mock_file_contents[SSM_DOCUMENTS_DIR + '/asiaq-ssm_document_1.ssm'] = new_doc_1_content
        mock_open.side_effect = create_mock_open(mock_file_contents)

        # Calling the method under test
        self._ssm.update(wait=False)

        # Verify only document_1 is modified
        self.assertEquals(_standardize_json_str(new_doc_1_content),
                          _standardize_json_str(
                              self._ssm.get_document_content('asiaq-ssm_document_1')))
        self.assertEquals(_standardize_json_str(MOCK_ASIAQ_DOCUMENT_CONTENTS['asiaq-ssm_document_2']),
                          _standardize_json_str(
                              self._ssm.get_document_content('asiaq-ssm_document_2')))

    @patch('boto3.client', mock_boto3_client)
    @patch('os.listdir')
    @patch('disco_aws_automation.disco_ssm.open')
    @patch('disco_aws_automation.disco_ssm.SSM_WAIT_TIMEOUT')
    @patch('disco_aws_automation.disco_ssm.SSM_WAIT_SLEEP_INTERVAL')
    def test_update_modify_docs_wait(self, mock_wait_interval, mock_wait_timeout,
                                     mock_open, mock_os_listdir):
        """Verify that modifying documents in the update() method works with wait set to true"""
        # Setting up test
        mock_os_listdir.return_value = ['asiaq-ssm_document_1.ssm', 'asiaq-ssm_document_2.ssm',
                                        'random_file1.txt', 'random_file2.jpg']

        new_doc_1_content = '{"random_field_1": "random_value_1"}'
        mock_file_contents = copy.copy(MOCK_ASIAQ_DOCUMENT_FILE_CONTENTS)
        mock_file_contents[SSM_DOCUMENTS_DIR + '/asiaq-ssm_document_1.ssm'] = new_doc_1_content
        mock_open.side_effect = create_mock_open(mock_file_contents)
        mock_wait_timeout.return_value = 1
        mock_wait_interval.return_value = 1

        # Calling the method under test
        self._ssm.update(wait=True)

        # Verify only document_1 is modified
        describe_call = call(Name='asiaq-ssm_document_1')
        # Expecting describe_document() to be called four times: two for delete, two for create
        expected_describe_calls = [describe_call, describe_call, describe_call, describe_call]
        self.assertEquals(expected_describe_calls,
                          self._ssm.conn.describe_document.mock_calls)

        self.assertEquals(_standardize_json_str(new_doc_1_content),
                          _standardize_json_str(
                              self._ssm.get_document_content('asiaq-ssm_document_1')))
        self.assertEquals(_standardize_json_str(MOCK_ASIAQ_DOCUMENT_CONTENTS['asiaq-ssm_document_2']),
                          _standardize_json_str(
                              self._ssm.get_document_content('asiaq-ssm_document_2')))
