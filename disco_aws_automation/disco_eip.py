"""
Some code to manage elastic IP's.  Elastic IP's are fixed internet routable addresses
that we can assign to our AWS instances.  We use them for certain hostclasses, such as Jenkins.
"""
from boto.vpc import VPCConnection


class DiscoEIP(object):
    """
    A simple class to manage EIP's
    """

    def __init__(self):
        self.vpc_conn = VPCConnection()

    def list(self):
        """Returns all of our currently allocated EIPs"""
        return self.vpc_conn.get_all_addresses()

    def allocate(self):
        """Allocates a new VPC EIP"""
        return self.vpc_conn.allocate_address(domain='vpc')

    def release(self, eip_address, force=False):
        """
        Releases an EIP.

        If it is currently associated with a machine we do not release it unless
        the force param is set.
        """
        eip = self.vpc_conn.get_all_addresses([eip_address])[0]

        if eip.association_id:
            if force:
                eip.disassociate()
            else:
                return False

        return eip.release()
