User IAM policies and trust relationships
=========================================

This directory contains files which specify the IAM policy of a role.
These end in .iam

This directory optionally contains the trust relationship of a role.
These end in .tr

And role not containing a trust relationship file will get the trust
relationship contained in iam/federation/AssumeRolePolicyDocument.iam
applied as the trust relationship of the role.
