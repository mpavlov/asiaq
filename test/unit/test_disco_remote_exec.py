"""
Tests of disco_remote_exec
"""
import unittest

from mock import MagicMock, patch

from disco_aws_automation import CommandError
from disco_aws_automation.disco_remote_exec import DiscoRemoteExec

TEST_DEFAULT_SSH_OPTIONS = '-oConnectTimeout=10 -oBatchMode=yes -oStrictHostKeyChecking=no " \
                 "-oUserKnownHostsFile=/dev/null'
TEST_ADDRESS = '123.123.123.123'
TEST_USER = 'unit_test_user'
TEST_JUMP_ADDRESS = '100.100.100.100'
TEST_COMMAND = ['ls']
TEST_COMMAND_STR = ' '.join(TEST_COMMAND)
TEST_PROXY_HOP = "ssh -oConnectTimeout=10 -oBatchMode=yes -oStrictHostKeyChecking=no " \
                 "-oUserKnownHostsFile=/dev/null -l%s %s '%s'" % (TEST_USER, TEST_ADDRESS, TEST_COMMAND_STR)


def _get_mock_process():
    process = MagicMock()
    process.returncode = 0

    return process


class DiscoRemoteExecTests(unittest.TestCase):
    """Tests of disco_remote_exec"""

    # the patch decorator automatically gives us the Mock instances as arguments even if we don't need them
    # pylint: disable=unused-argument
    @patch('disco_aws_automation.disco_remote_exec.DiscoRemoteExec._is_reachable', return_value=False)
    def test_unreachable_host(self, mock_is_reachable):
        """test that a exception is thrown if a host is unreachable and there is no jump address"""
        self.assertRaises(CommandError, DiscoRemoteExec.remotecmd,
                          address=TEST_ADDRESS,
                          remote_command=TEST_COMMAND,
                          user=TEST_USER)

    # pylint: disable=unused-argument
    @patch('disco_aws_automation.disco_remote_exec.DiscoRemoteExec._is_reachable', return_value=True)
    @patch('disco_aws_automation.disco_remote_exec.DiscoRemoteExec._get_remote_exec_command')
    @patch('subprocess.Popen', return_value=_get_mock_process())
    def test_jump_address_reachable_host(self, mock_popen, mock_get_exec_command, mock_is_reachable):
        """test that jump address is not used for reachable host"""
        DiscoRemoteExec.remotecmd(address=TEST_ADDRESS,
                                  remote_command=TEST_COMMAND,
                                  user=TEST_USER,
                                  jump_address=TEST_JUMP_ADDRESS)

        mock_get_exec_command.assert_called_once_with(TEST_ADDRESS, TEST_COMMAND, TEST_USER, None, (), None)

    # pylint: disable=unused-argument
    @patch('disco_aws_automation.disco_remote_exec.DiscoRemoteExec._is_reachable', return_value=False)
    @patch('disco_aws_automation.disco_remote_exec.DiscoRemoteExec._get_remote_exec_command')
    @patch('subprocess.Popen', return_value=_get_mock_process())
    def test_jump_address_unreachable_host(self, mock_popen, mock_get_exec_command, mock_is_reachable):
        """test that jump address is used for an unreachable host"""
        DiscoRemoteExec.remotecmd(address=TEST_ADDRESS,
                                  remote_command=TEST_COMMAND,
                                  user=TEST_USER,
                                  jump_address=TEST_JUMP_ADDRESS)

        mock_get_exec_command.assert_called_once_with(TEST_ADDRESS, TEST_COMMAND, TEST_USER,
                                                      TEST_JUMP_ADDRESS, (), None)

    def test_arguments_simple(self):
        """test getting ssh arguments with minimal options"""
        command = DiscoRemoteExec._get_remote_exec_command(address=TEST_ADDRESS,
                                                           remote_command=TEST_COMMAND,
                                                           user=TEST_USER,
                                                           jump_address=None,
                                                           ssh_options=[],
                                                           forward_agent=False)

        expected = ['ssh',
                    '-oConnectTimeout=10',
                    '-oBatchMode=yes',
                    '-oStrictHostKeyChecking=no',
                    '-oUserKnownHostsFile=/dev/null',
                    '-l%s' % TEST_USER,
                    TEST_ADDRESS,
                    TEST_COMMAND_STR]

        self.assertEquals(command, expected)

    def test_arguments_with_jump_address(self):
        """test getting ssh arguments when using a jump box"""
        command = DiscoRemoteExec._get_remote_exec_command(address=TEST_ADDRESS,
                                                           remote_command=TEST_COMMAND,
                                                           user=TEST_USER,
                                                           jump_address=TEST_JUMP_ADDRESS,
                                                           ssh_options=[],
                                                           forward_agent=False)

        expected = ['ssh',
                    '-A',
                    '-t',
                    '%s@%s' % (TEST_USER, TEST_JUMP_ADDRESS),
                    '-oConnectTimeout=10',
                    '-oBatchMode=yes',
                    '-oStrictHostKeyChecking=no',
                    '-oUserKnownHostsFile=/dev/null',
                    TEST_PROXY_HOP]

        self.assertEquals(command, expected)

    def test_arguments_with_forward_agent(self):
        """test getting ssh arguments when forwarding ssh agent"""
        command = DiscoRemoteExec._get_remote_exec_command(address=TEST_ADDRESS,
                                                           remote_command=TEST_COMMAND,
                                                           user=TEST_USER,
                                                           jump_address=None,
                                                           ssh_options=[],
                                                           forward_agent=True)
        expected = ['ssh',
                    '-oConnectTimeout=10',
                    '-oBatchMode=yes',
                    '-oStrictHostKeyChecking=no',
                    '-oUserKnownHostsFile=/dev/null',
                    '-A',
                    '-l%s' % TEST_USER,
                    TEST_ADDRESS,
                    TEST_COMMAND_STR]

        self.assertEquals(command, expected)

    def test_arguments_with_ssh_options(self):
        """test getting ssh arguments when forwarding ssh agent"""
        command = DiscoRemoteExec._get_remote_exec_command(address=TEST_ADDRESS,
                                                           remote_command=TEST_COMMAND,
                                                           user=TEST_USER,
                                                           jump_address=None,
                                                           ssh_options=['-foo'],
                                                           forward_agent=False)
        expected = ['ssh',
                    '-oConnectTimeout=10',
                    '-oBatchMode=yes',
                    '-oStrictHostKeyChecking=no',
                    '-oUserKnownHostsFile=/dev/null',
                    '-l%s' % TEST_USER,
                    TEST_ADDRESS,
                    '-foo',
                    TEST_COMMAND_STR]

        self.assertEquals(command, expected)
