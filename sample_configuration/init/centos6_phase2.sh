#!/bin/bash -xe
# vim: ts=4 sw=4 et

####
# This init is used to configure the hostclass specific ami. That is take a
# phase1 AMI, unpack config and install hostclass specific software.
####

#Make sure we set our hostname from user-data if passed in
chkconfig --add hostname
chkconfig hostname on

#Add s3proxy into /etc/hosts,so we don't to depend on s3proxy server to update DNS entry
chkconfig disco-add-etc-hosts on

#Fetch credentials from S3 (a no-op for hosts that don't have the appropriate IAM role)
chkconfig disco-update-creds on

#Tag instance with userdata
chkconfig disco-tag-instance on

#Ensure SmartStack reporting is enabled on all hosts
chkconfig nerve on

#Enable ENI stealing and customized routing
chkconfig disco-associate-eni on
chkconfig disco-ip-route on

# Grab our EIP on boot, release on shutdown
chkconfig disco-associate-eip on

# Install the AWS root key if present (we do this early to aid debugging).
chkconfig --add download-root-key
chkconfig download-root-key on

if [[ "$HAS_REPO" == "1" ]] ; then
    #Install disco_aws_automation on repo dependent hosts
    yum_install asiaq

    #Add unix users for human operators, depends on disco_aws_automation
    chkconfig disco-add-operators on

    #SmartStack uses haproxy and needs newish haproxy, install and enable it
    yum_install haproxy # install the latest from our repos
    `dirname $0`/initmunge.py --provides haproxy \
                              --default-start "1 2 3 4 5" \
                              --default-stop "0 6" \
                              /etc/init.d/haproxy
    chkconfig haproxy on

    #Enable SmartStack discovery on all hosts with haproxy
    chkconfig synapse on
fi

hostclass_init="$discoaws_init_path/$hostclass.sh"
if [ -x "$hostclass_init" ]; then
    if [[ "$HAS_REPO" != "1" ]]; then
        disable_internal_repos
    fi

    "$hostclass_init"

    enable_internal_repos
else
    echo "No hostclass specific init found. Exiting."
    exit 1
fi

# enable shell access auditing
`dirname $0`/rootsh.sh

#Remove disco repo, they won't work after the machines are provisioned anyway..
rm -Rf /etc/yum.repos.d/*sample_project* /etc/yum.repos.d/*backports*
# Use proxy for yum traffic. NOTE, we don't use proxy for baking this is to make
# yum work in CI.
echo "enableProxy=1" >> /etc/yum.conf
echo "httpProxy=http://s3proxy/" >> /etc/yum.conf
