#!/bin/bash -xe
# vim: ts=4 sw=4 et

# rootsh logs all commands entered in the terminal, and their output, to syslog for auditing purposes
# TODO: rootsh logs to local5 at the notice level. We should raise the log level because when syslog queues get filled up it will start
# dropping messages with lowest priority first. The challenge is that this setting can only be changed at compile time.
yum -y --disablerepo="*sample_project*" --disablerepo="*backports*" install rootsh

# Replace the default login shell with rootsh. This prevents the user from just exiting
# out of rootsh into the (insecure) default shell.
# More on setting rootsh as the default login shell: http://www.tmltechnologies.com/html-2012/index.php/linux-rescue-kits/82-secret/133-pci-dss-requirement-10-part1-logging-with-rootsh
echo "exec /usr/bin/rootsh --no-logfile" >> /etc/profile
