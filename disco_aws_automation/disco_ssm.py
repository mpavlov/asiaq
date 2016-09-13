"""
Manage AWS SSM document creation and execution
"""
import os
import logging
import time
import json

import boto3
from botocore.exceptions import ClientError

from . import read_config
from .resource_helper import throttled_call, wait_for_state_boto3
from .exceptions import TimeoutError

logger = logging.getLogger(__name__)


SSM_DOCUMENTS_DIR = "ssm/documents"
SSM_EXT = ".ssm"
SSM_WAIT_TIMEOUT = 5 * 60
SSM_WAIT_SLEEP_INTERVAL = 15
AWS_DOCUMENT_PREFIX = "AWS-"


class DiscoSSM(object):
    """
    A simple class to manage SSM documents
    """

    def __init__(self, environment_name=None, config_aws=None):
        self.config_aws = config_aws or read_config()

        if environment_name:
            self.environment_name = environment_name.lower()
        else:
            self.environment_name = self.config_aws.get("disco_aws", "default_environment")

        self._conn = None  # Lazily initialized

    @property
    def conn(self):
        """The boto3 ssm connection object"""
        if not self._conn:
            self._conn = boto3.client('ssm')
        return self._conn

    def get_all_documents(self):
        """ Returns a list of existing SSM documents."""
        next_token = ''
        documents = []
        while True:
            if next_token:
                response = throttled_call(self.conn.list_documents, NextToken=next_token)
            else:
                response = throttled_call(self.conn.list_documents)

            documents.extend(response.get("DocumentIdentifiers"))
            next_token = response.get("NextToken")

            if not next_token:
                break

        result = [doc for doc in documents
                  if self._check_valid_doc_prefix(doc["Name"])]
        return result

    def get_document_content(self, doc_name):
        """ Returns the content of the document."""
        if not self._check_valid_doc_prefix(doc_name):
            raise Exception("Document name ({0}) has an invalid prefix.".format(doc_name))

        try:
            response = throttled_call(self.conn.get_document, Name=doc_name)
        except ClientError:
            logger.info("Document name (%s) is not found.", doc_name)
            return None

        return response.get("Content")

    def update(self, wait=False, dry_run=False):
        """ Updates SSM documents from configuration """
        desired_docs = set(self._list_docs_in_config())
        existing_docs = set([doc["Name"] for doc in self.get_all_documents()])

        docs_to_create = desired_docs - existing_docs
        docs_to_delete = existing_docs - desired_docs
        docs_to_update = self._check_for_update(desired_docs & existing_docs)
        unchanged_docs = existing_docs - docs_to_update - docs_to_delete

        logger.info("New documents to be added: %s", docs_to_create)
        logger.info("Documents to be deleted: %s", docs_to_delete)
        logger.info("Existing documents to be updated: %s", docs_to_update)
        logger.info("Unchanged documents: %s", unchanged_docs)

        if not dry_run:
            # Include docs_to_update in docs_to_delete so that they can be recreated later
            docs_to_delete |= docs_to_update
            self._delete_docs(docs_to_delete)
            if wait:
                self._wait_for_docs_deleted(docs_to_delete)

            docs_to_create |= docs_to_update
            self._create_docs(docs_to_create)
            if wait:
                self._wait_for_docs_active(docs_to_create)

    def _create_docs(self, docs_to_create):
        for doc_name in docs_to_create:
            ssm_json = self._read_ssm_file(doc_name)
            logger.debug("Creating document: %s", doc_name)
            throttled_call(self.conn.create_document, Content=ssm_json, Name=doc_name)

    def _delete_docs(self, docs_to_delete):
        for doc_name in docs_to_delete:
            logger.debug("Deleting document: %s", doc_name)
            throttled_call(self.conn.delete_document, Name=doc_name)

    def _check_for_update(self, docs_to_check):
        """
        Returns the documents whose content in the configuration is different from
        the one currently in AWS
        """
        docs_to_update = set()
        for doc_name in docs_to_check:
            desired_json = self._read_ssm_file(doc_name)
            existing_json = self._standardize_json_str(self.get_document_content(doc_name))

            if desired_json != existing_json:
                docs_to_update.add(doc_name)

        return docs_to_update

    def _wait_for_docs_deleted(self, docs_to_delete):
        for doc_name in docs_to_delete:
            time_passed = 0

            while True:
                try:
                    self.conn.describe_document(Name=doc_name)
                except ClientError:
                    # When the document is deleted, calling the describe method would
                    # result in a ClientError being thrown, that's when we know the document
                    # has been deleted.
                    break

                if time_passed >= SSM_WAIT_TIMEOUT:
                    raise TimeoutError(
                        "Timed out waiting for document ({0}) to be deleted after {1}s"
                        .format(doc_name, time_passed))

                time.sleep(SSM_WAIT_SLEEP_INTERVAL)
                time_passed += SSM_WAIT_SLEEP_INTERVAL

    def _wait_for_docs_active(self, docs_to_wait):
        for doc_name in docs_to_wait:
            wait_for_state_boto3(describe_func=self.conn.describe_document,
                                 params_dict={"Name": doc_name},
                                 resources_name="Document",
                                 expected_state="Active",
                                 state_attr="Status",
                                 timeout=SSM_WAIT_TIMEOUT)

    def _read_ssm_file(self, doc_name):
        file_path = "{0}/{1}{2}".format(SSM_DOCUMENTS_DIR, doc_name, SSM_EXT)
        with open(file_path, 'r') as infile:
            ssm_content = infile.read()

        try:
            return self._standardize_json_str(ssm_content)
        except ValueError:
            raise RuntimeError("Invalid SSM document file: {0}".format(file_path))

    def _standardize_json_str(self, json_str):
        return json.dumps(json.loads(json_str), indent=4)

    def _list_docs_in_config(self):
        document_files = os.listdir(SSM_DOCUMENTS_DIR)
        return [document[:-len(SSM_EXT)]
                for document in document_files
                if document.endswith(SSM_EXT) and self._check_valid_doc_prefix(document)]

    def _check_valid_doc_prefix(self, doc_name):
        return not doc_name.startswith(AWS_DOCUMENT_PREFIX)
