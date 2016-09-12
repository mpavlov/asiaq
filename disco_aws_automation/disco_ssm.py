"""
Manage AWS SSM document creation and execution
"""
import logging
import time
import json
from ConfigParser import NoOptionError

import boto3

from . import read_config
from .disco_creds import DiscoS3Bucket
from .resource_helper import throttled_call
from .disco_constants import (
    DEFAULT_CONFIG_SECTION
)

logger = logging.getLogger(__name__)


class DiscoSSM(object):
    """
    A simple class to manage SSM documents
    """

    def __init__(self, environment_name, config_aws=None):
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

    def get_s3_bucket_name(self):
        """Convenience method for returning the configured s3 bucket for SSM"""
        return self.get_aws_option_default("ssm_s3_bucket", default=None)

    def execute(self, instance_ids, document_name, parameters=None, comment=None):
        """
        Executes the given SSM document against a given list of instance ids.

        Optionally takes parameters to pass to the SSM document and an audit comment to indicate why this
        command was run.
        """
        bucket_name = self.get_s3_bucket_name()

        arguments = {
            "InstanceIds": instance_ids,
            "DocumentName": document_name
        }

        if parameters is not None:
            arguments["Parameters"] = parameters

        if comment is not None:
            arguments["Comment"] = comment

        if bucket_name is not None:
            arguments["OutputS3BucketName"] = bucket_name

        logger.info(
            "Executing document '%s' against instances %s",
            document_name,
            instance_ids
        )

        command = self._send_command(**arguments)
        command_id = command["Command"]["CommandId"]

        is_successful = self._wait_for_ssm_command(command_id=command_id)

        output = self.get_ssm_command_output(command_id=command_id)

        self._print_ssm_output(output)

        return is_successful

    def _print_ssm_output(self, output):
        """Convenience method for printing output from an SSM command"""
        for instance, instance_output in output.iteritems():
            print("Output for instance: {}".format(instance))
            for plugin in instance_output:
                print(
                    u"Plugin: {}\n\n"
                    u"STDOUT:\n{}\n\n"
                    u"STDERR:\n{}\n\n"
                    u"Exit Code: {}".format(
                        plugin.get('name', '-'),
                        plugin.get('stdout', '-'),
                        plugin.get('stderr', '-'),
                        plugin.get('exit_code')
                    )
                )

    def _wait_for_ssm_command(self, command_id, desired_status='Success', timeout=600):
        """
        Method for waiting for the completion of a given command. Requires the command_id as well as an
        optional desired_status and a timeout value in seconds.

        Defaults to a desired status of 'Success' and a timeout of 600 seconds.

        See http://docs.aws.amazon.com/ssm/latest/APIReference/API_Command.html#EC2-Type-Command-Status
        for the valid values of desired_status.

        Note that this method only waits for the desired status to NOT be 'Pending' or 'InProgress'. In other
        words, once the command terminates this method will either return True if the status of the command
        equals the desired status, or False otherwise. For example, the command could be cancelled before it
        completes, it could timeout, or it could return a non-zero exit code.
        """
        stop_time = time.time() + timeout
        while time.time() < stop_time:
            command = self._list_commands(
                CommandId=command_id
            )
            status = command["Commands"][0]["Status"]
            document_name = command["Commands"][0]["DocumentName"]
            instance_ids = command["Commands"][0]["InstanceIds"]
            # If the command is not waiting to execute or executing, let's see if we got the status we wanted
            if status not in ['Pending', 'InProgress']:
                logger.info(
                    "Execution of document '%s' against instances %s completed as '%s'",
                    document_name,
                    instance_ids,
                    status
                )
                return status == desired_status
            logger.info(
                "Waiting for execution of document '%s' against instances %s",
                document_name,
                instance_ids
            )
            time.sleep(5)
        raise TimeoutException(
            "Timed out waiting for execution of document '%s' against instances %s after '%s' seconds".format(
                document_name,
                instance_ids,
                timeout
            )
        )

    def get_ssm_command_output(self, command_id):
        """
        Method for getting the output of a given command. Requires the command_id of the desired command.

        Returns a dictionary object, in the form of:

        {
            "i-c3dfed1e": [
                {
                    "name": <plugin name>,
                    "stdout": <stdout>,
                    "stderr": <stderr>,
                    "exit_code": <exit code>
                },
                ...
            ],
            ...
        }

        """
        command_invocations = self._list_command_invocations(
            CommandId=command_id,
            Details=True
        )

        response = {}

        for command_invocation in command_invocations["CommandInvocations"]:
            instance_id = command_invocation['InstanceId']
            instance_output = []

            for command_plugin in command_invocation['CommandPlugins']:
                if 'OutputS3BucketName' in command_plugin.keys():
                    plugin_output = self._get_output_from_s3(command_plugin)
                else:
                    plugin_output = self._get_output_from_ssm(command_plugin)

                instance_output.append(plugin_output)

            response[instance_id] = instance_output

        return response

    def _get_output_from_ssm(self, command_plugin):
        """Helper method for extracting command output directly from SSM"""
        output = command_plugin['Output'].split('----------ERROR-------')
        stdout = output[0].strip() or '-'

        if len(output) == 2:
            stderr = output[1].strip()
        else:
            stderr = '-'

        plugin_output = {
            'name': command_plugin['Name'],
            'stdout': stdout,
            'stderr': stderr,
            'exit_code': command_plugin['ResponseCode']
        }

        return plugin_output

    def _get_output_from_s3(self, command_plugin, s3_bucket=None):
        """Helper method for extracting command output from S3"""
        bucket_name = command_plugin['OutputS3BucketName']
        key = command_plugin['OutputS3KeyPrefix']
        bucket = s3_bucket or DiscoS3Bucket(bucket_name)

        keys_from_command = bucket.listkeys(prefix_keys=key)

        stdout_keys = [key for key in keys_from_command if key.endswith('stdout')]
        stderr_keys = [key for key in keys_from_command if key.endswith('stderr')]

        if stdout_keys:
            stdout = bucket.get_key(stdout_keys[0]).decode('utf-8').strip()
        else:
            stdout = '-'

        if stderr_keys:
            stderr = bucket.get_key(stderr_keys[0]).decode('utf-8').strip()
        else:
            stderr = '-'

        plugin_output = {
            'name': command_plugin['Name'],
            'stdout': stdout,
            'stderr': stderr,
            'exit_code': command_plugin['ResponseCode']
        }

        return plugin_output

    def _send_command(self, **arguments):
        """Convenience method for sending SSM commands"""
        return throttled_call(self.conn.send_command, **arguments)

    def _list_commands(self, **arguments):
        """Convenience method for listing SSM commands"""
        return throttled_call(self.conn.list_commands, **arguments)

    def _list_command_invocations(self, **arguments):
        """Convenience method for listing invocations of SSM commands"""
        return throttled_call(self.conn.list_command_invocations, **arguments)

    def get_aws_option(self, option, section=DEFAULT_CONFIG_SECTION):
        """Get a value from the config"""
        env_option = "{0}@{1}".format(option, self.environment_name)
        default_option = "default_{0}".format(option)
        default_env_option = "default_{0}".format(env_option)

        if self.config_aws.has_option(section, env_option):
            return self.config_aws.get(section, env_option)
        if self.config_aws.has_option(section, option):
            return self.config_aws.get(section, option)
        elif self.config_aws.has_option(DEFAULT_CONFIG_SECTION, default_env_option):
            return self.config_aws.get(DEFAULT_CONFIG_SECTION, default_env_option)
        elif self.config_aws.has_option(DEFAULT_CONFIG_SECTION, default_option):
            return self.config_aws.get(DEFAULT_CONFIG_SECTION, default_option)

        raise NoOptionError(option, section)

    def get_aws_option_default(self, option, section=DEFAULT_CONFIG_SECTION, default=None):
        """Get a value from the config"""
        try:
            return self.get_aws_option(option, section)
        except NoOptionError:
            return default
