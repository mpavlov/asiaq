"""
This module has utility functions for working with networks
"""

from math import ceil, log


def calc_subnet_offset(num_subnets):
    """
    Calculate the size difference between a network and its subnets if there are a certain number of
    equally sized subnets


    Returns (int): The difference in cidr bits of a network and the subnets.
                   For example breaking a /20 network into 4 subnets will create /22 subnets returning 2.

    """
    return int(ceil(log(num_subnets, 2)))
