"""
Some helpers for integration tests
"""
import subprocess
import logging
import os
import re
from functools import wraps
from unittest import TestCase
from StringIO import StringIO

import boto


TEST_HOSTCLASS = "mhcntp"

CREATE_AMI_EXPR = re.compile(r"Created.*?AMI (?P<ami_id>ami-\w+)")


def cleanup_amis(func):
    '''This captures the standard output of an integration test and cleans up any created AMIs'''
    @wraps(func)
    def _capture_and_cleanup_wrapper(self, *args, **kwargs):

        captured_stdout = StringIO()
        try:
            func(self, captured_stdout, *args, **kwargs)
        except:
            captured_stdout.seek(0)
            logging.error(captured_stdout.read())
            raise
        finally:
            self.cleanup_created_amis(captured_stdout)

    return _capture_and_cleanup_wrapper


class IntegrationTest(TestCase):
    '''Base class for our integration tests'''

    @classmethod
    def setUpClass(cls):
        cls.connect = boto.connect_ec2()

    def cleanup_created_amis(self, captured_stdout):
        '''Used by the integration decorator to clean up AMIs'''
        captured_stdout.seek(0)
        for line in captured_stdout:
            ami_id = self.get_ami_id(line)
            if ami_id:
                try:
                    if self.connect.get_all_images(image_ids=[ami_id]):
                        self.connect.deregister_image(ami_id)
                except Exception as err:
                    logging.exception("Received exception %s when trying to delete ami %s", err, ami_id)

    @staticmethod
    def run_cmd(command, captured_stdout=None, quiet=False):
        """
        Runs a shell command. Raises on failure unless ``quiet == True``.
        Returns stdout output; stderr is redirected to stdout.
        Output is also appended to the stream ``captured_stdout``, if one is supplied.
        """
        captured_stdout = captured_stdout or StringIO()
        command = command.split() if isinstance(command, basestring) else command
        print ">>> {}".format(" ".join(command))
        process = subprocess.Popen(command,
                                   stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT,
                                   env=os.environ.copy())  # relay ASIAQ_CONFIG and any other env vars

        output = process.communicate()[0]
        captured_stdout.write(output)

        if not quiet and process.returncode:
            logging.info(output)  # show failure details to whoever's running the test
            raise RuntimeError("Command %s failed" % " ".join(command))
        else:
            return output

    @staticmethod
    def get_ami_id(output):
        """
        Returns the id of the first created AMI found in output.
        """
        match = CREATE_AMI_EXPR.search(output)
        return match.group("ami_id") if match else None
