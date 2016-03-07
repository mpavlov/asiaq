"""
Integration tests for disco_dynamodb.py
"""

import json
from random import randint
from test.helpers.integration_helpers import IntegrationTest


MOCK_TABLE_NAME = "IntegrationTest"
CREATE_CMD = "disco_dynamodb.py create --env {0} --config test/test_dynamodb_create.json --wait"
DELETE_CMD = "disco_dynamodb.py delete --table {0} --env {1} --wait"
LIST_CMD = "disco_dynamodb.py list"


class TestDiscoDynamoDB(IntegrationTest):
    """ Test bin/disco_dynamodb.py """

    def setUp(self):
        """
        Generate random environment name for integration test env
        """
        self.env_name = "env_{0}".format(randint(10000, 99999))

    def test_create_and_delete_table(self):
        """ Ensures we can create and delete DynamoDB table properly """
        table_list_output = u"{0:<20} {1}".format(MOCK_TABLE_NAME, self.env_name)

        try:
            create_output = self.run_cmd(CREATE_CMD.format(self.env_name).split())

            table = json.loads(create_output)

            self.assertEqual(table["TableStatus"], "ACTIVE")
            self.assertEqual(table["TableName"], "{0}_{1}".format(MOCK_TABLE_NAME, self.env_name))
            self.assertEqual(table["ProvisionedThroughput"]["WriteCapacityUnits"], 10)
            self.assertEqual(table["ProvisionedThroughput"]["ReadCapacityUnits"], 10)
            for key in table["KeySchema"]:
                if key["KeyType"] == "HASH":
                    self.assertEqual(key["AttributeName"], "_id")
                else:
                    self.assertEqual(key["AttributeName"], "mock_range_key")

            self.assertEqual(table["GlobalSecondaryIndexes"][0]["IndexName"], "mock_index")
            self.assertEqual(table["GlobalSecondaryIndexes"][0]["KeySchema"][0]["AttributeName"],
                             "mock_index_attr")
            self.assertEqual(table["GlobalSecondaryIndexes"][0]["Projection"]["ProjectionType"], "ALL")

            # Also assert that table can be found when running the list command
            list_output = self.run_cmd(LIST_CMD.format(self.env_name).split())
            lines = list_output.split('\n')
            self.assertIn(table_list_output, lines)
        finally:
            delete_output = self.run_cmd(DELETE_CMD.format(MOCK_TABLE_NAME, self.env_name).split())
            delete_output = json.loads(delete_output)

            self.assertEqual(delete_output["TableName"], "{0}_{1}".format(MOCK_TABLE_NAME, self.env_name))
            self.assertEqual(delete_output["TableStatus"], "DELETED")

        list_output = self.run_cmd(LIST_CMD.format(self.env_name).split())
        lines = list_output.split('\n')
        self.assertNotIn(table_list_output, lines)
