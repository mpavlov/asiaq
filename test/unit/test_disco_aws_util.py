"""
Tests of disco_aws_util
"""
from unittest import TestCase

from disco_aws_automation import disco_aws_util


class DiscoAWSUtilTests(TestCase):
    '''Test disco_aws_util.py'''


    def test_size_as_rec_map_with_none(self):
        """_size_as_recurrence_map works with None"""
        self.assertEqual(disco_aws_util.size_as_recurrence_map(None), {"": None})
        self.assertEqual(disco_aws_util.size_as_recurrence_map(''), {"": None})

    def test_size_as_rec_map_with_int(self):
        """_size_as_recurrence_map works with simple integer"""
        self.assertEqual(disco_aws_util.size_as_recurrence_map(5, sentinel="0 0 * * *"),
                         {"0 0 * * *": 5})

    def test_size_as_rec_map_with_map(self):
        """_size_as_recurrence_map works with a map"""
        map_as_string = "2@1 0 * * *:3@6 0 * * *"
        map_as_dict = {"1 0 * * *": 2, "6 0 * * *": 3}
        self.assertEqual(disco_aws_util.size_as_recurrence_map(map_as_string), map_as_dict)

    def test_size_as_rec_map_with_duped_map(self):
        """_size_as_recurrence_map works with a duped map"""
        map_as_string = "2@1 0 * * *:3@6 0 * * *:3@6 0 * * *"
        map_as_dict = {"1 0 * * *": 2, "6 0 * * *": 3}
        self.assertEqual(disco_aws_util.size_as_recurrence_map(map_as_string), map_as_dict)
