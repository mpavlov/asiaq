"""
Container for disco_aws_automation exceptions
"""


class TimeoutError(RuntimeError):
    """Error raised on timeout"""
    pass


class ExpectedTimeoutError(TimeoutError):
    """
    Error raised in situations where we decide to terminate
    the keep-trying loop early because we have learned that
    the chance of success is 0%
    """
    pass


class EarlyExitException(Exception):
    "Special no-op Exception class for non-error early exits from the program."
    pass


class AccountError(Exception):
    """ Account manipulation error """
    pass


class CommandError(RuntimeError):
    """ Error running SSH command """
    pass


class MaintenanceModeError(RuntimeError):
    """ Error entering or leaving maintenance mode """
    pass


class IntegrationTestError(RuntimeError):
    """ Error running integration tests """
    pass


class VPCEnvironmentError(RuntimeError):
    """ Error relating to accessing environment """
    pass


class SmokeTestError(RuntimeError):
    """ Error while performing smoketest """
    pass


class AMIError(RuntimeError):
    """ Amazon Machine Image Error """
    pass


class VolumeError(RuntimeError):
    """S3 Volume Error"""
    pass


class InstanceMetadataError(RuntimeError):
    """Instance Metadata Error"""
    pass


class IPRangeError(RuntimeError):
    """IP not in rage error"""
    pass


class WrongPathError(RuntimeError):
    """Not executed in the right path"""
    pass


class S3WritingError(RuntimeError):
    """S3 object is not written correctly"""
    pass


class MissingAppAuthError(RuntimeError):
    """Application Authorization files is not found"""
    pass


class AppAuthKeyNotFoundError(RuntimeError):
    """Application Authorization Key is not found"""
    pass


class VPCPeeringSyntaxError(RuntimeError):
    """VPC Peering syntax is incorrect"""
    pass


class VPCConfigError(RuntimeError):
    """VPC config is incorrect"""
    pass


class MultipleVPCsForVPCNameError(RuntimeError):
    """Found multiple VPCs with the same name"""
    pass


class VPCNameNotFound(RuntimeError):
    """Can't find VPC by the name"""
    pass


class DynamoDBEnvironmentError(RuntimeError):
    """DynamoDB Generic Error"""
    pass


class AlarmConfigError(RuntimeError):
    """Error in Alarm Configuration"""
    pass


class RDSEnvironmentError(RuntimeError):
    """RDS Generic Error"""
    pass


class EIPConfigError(RuntimeError):
    """Error in Elastic IP Configuration"""
    pass


class RouteCreationError(RuntimeError):
    """Error trying to create a route"""
    pass
