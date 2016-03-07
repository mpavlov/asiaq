#!/bin/false

DISCO_OS="unknown"
if [[ $(grep Ubuntu /etc/*-release > /dev/null ; echo $?) == "0" ]] ; then
    DISCO_OS="ubuntu"
elif [[ -e /etc/centos-release ]] ; then
    DISCO_OS="centos"
    DISCO_OS_VERSION=$(sed -n 's/.*release \([0-9]*\)\..*/\1/p' '/etc/centos-release')
fi
export DISCO_OS
export DISCO_OS_VERSION

yum_install() {
    local package
    for package in $@; do
        yum -y install $package
    done
}

disable_internal_repos() {
    if [[ "$DISCO_OS" == "centos" ]] ; then
        yum install -y yum-utils --disablerepo="*sample_project*" --disablerepo="*backports*"
        yum-config-manager --disable "*sample_project*" --disable "*backports*"
    fi
}

enable_internal_repos() {
    if [[ "$DISCO_OS" == "centos" ]] ; then
        yum-config-manager --enable "*sample_project*" --enable "*backports*"
    fi
}

disable_proxy() {
    echo "" > /etc/profile.d/proxy.sh
}

init_system_user() {
    # Create a unix system account
    # Params username [shell] [uid]
    local user="$1"
    local shell=${2:-/sbin/nologin}
    local uid="$3"

    if [ "$shell" != "/bin/bash" ] && [ "$shell" != "/sbin/nologin" ] ; then
        echo "Unapproved shell ($shell) used in init_system_user"
        exit 1
    fi

    # Allow user to specify a UID between 20000 (arbitrary) and 60000 (UID_MAX defined in /etc/login.defs).
    if [ ! -z "$uid" ]; then
        if [ "$uid" -ge "20000" ] && [ "$uid" -le "60000" ]; then
            local uid_flag="--uid $uid"
        else
            echo "Requested UID ($uid) outside of bounds (>= 20000 && <= 60000)"
            exit 2
        fi
    fi

    /usr/sbin/groupadd -f "$user"
    gid=$(getent group sys | cut -d: -f3)
    if ! /usr/bin/id $user &> /dev/null ; then
        /usr/sbin/adduser --gid "$gid" $uid_flag --system --shell "$shell" "$user"
    fi
}

init_one_command_user() {
    # Create a unix user account that only runs one command on ssh in
    # See: http://oreilly.com/catalog/sshtdg/chapter/ch08.html
    # Params: username command ssh_public_key
    local user="$1"
    local home="/home/$user"
    local command="$2"
    local key="$3"
    /usr/sbin/groupadd -f "$user"
    gid=$(getent group sys | cut -d: -f3)
    if ! /usr/bin/id $user &> /dev/null ; then
        if [[ "$DISCO_OS" == "ubuntu" ]] ; then
            /usr/sbin/adduser --home "$home" --gid "$gid" --shell "/bin/bash" "$user" --disabled-password
        else
            /usr/sbin/adduser --home "$home" --gid "$gid" --shell "/bin/bash" "$user"
        fi
    fi
    if [[ ("$key" != "") && ("$command" != "") ]]; then
        local ssh_dir="$home/.ssh"
        mkdir -p "$ssh_dir"
        echo "no-port-forwarding,command=\"$command\" $key" > "$ssh_dir/authorized_keys"

        chown -R $user:$user "$ssh_dir"
        chmod 700 "$ssh_dir"
        chmod 600 "$ssh_dir"/*
    fi
}

init_shell_user() {
    # Create a unix user account.
    # Params: username password ssh_public_key
    local user="$1"
    local home="/home/$user"
    local password="$2"
    local key="$3"
    /usr/sbin/groupadd -f "$user"
    gid=$(getent group sys | cut -d: -f3)
    if ! /usr/bin/id $user &> /dev/null ; then
        if [[ "$DISCO_OS" == "ubuntu" ]] ; then
            /usr/sbin/adduser --home "$home" --gid "$gid" --shell "/bin/bash" "$user" --disabled-password
        else
            /usr/sbin/adduser --home "$home" --gid "$gid" --shell "/bin/bash" "$user"
        fi
        echo -e "$password\n$password" | passwd "$user" > /dev/null
        /usr/sbin/usermod -G users "$user"
    fi
    if [ "$key" ]; then
        local ssh_dir="$home/.ssh"
        mkdir -p "$ssh_dir"
        echo "$key" >> "$ssh_dir/authorized_keys"
        chown -R $user:$user "$ssh_dir"
        chmod -R 700 "$ssh_dir"
    fi
}

function get_region() {
   local ZONE=$(curl --silent http://169.254.169.254/latest/meta-data/placement/availability-zone)
   local REGION=$(echo $ZONE | sed -e 's/.$//')
   echo $REGION
}

function install_awslogs() {
    # install AWS CloudWatch Log uploading agent
    pushd /tmp
    curl -OL "https://s3.amazonaws.com/aws-cloudwatch/downloads/latest/awslogs-agent-setup.py" > awslogs-agent-setup.py
    PIP_TRUSTED_HOST=repo PIP_INDEX_URL=http://repo/pypi/simple/ python awslogs-agent-setup.py -r $(get_region) -n -c /etc/awslogs.conf
    chkconfig awslogs on

    `dirname $0`/initmunge.py --required-start "discoawslogs" /etc/init.d/awslogs

    sed -e 's#/var/awslogs/bin/awslogs-agent-launcher.sh#/opt/wgen/bin/awslogs-agent-launcher.sh#g' \
        -i /etc/init.d/awslogs

    chkconfig disco-awslogs on
    popd
}

install_splunklogger() {
    # Download from splunk.com since this rpm is not available in any centos
    # repo and astro `repo` is not accessible in phase 1 bake. 
    curl -Lo splunkforwarder-4.3.7-181874-linux-2.6-x86_64.rpm \
    'http://www.splunk.com/page/download_track?file=4.3.7/universalforwarder/linux/splunkforwarder-4.3.7-181874-linux-2.6-x86_64.rpm&ac=&wget=true&name=wget&platform=Linux&architecture=x86_64&version=4.3.7&product=splunk&typed=release'

    rpm -ih splunkforwarder-4.3.7-181874-linux-2.6-x86_64.rpm

    # First time setup and accepting the licensing agreement. This created the
    # folder /opt/splunkforwarder and other default files which we will
    # override in the below
    /opt/splunkforwarder/bin/splunk start --accept-license --answer-yes --no-prompt

    # Setup the init scripts
    /opt/splunkforwarder/bin/splunk enable boot-start
    service splunk stop

    # splunkforwarder moved discoroot installed files to etc.bak, lets move it
    # back.
    cp -fR /opt/splunkforwarder/etc.bak/* /opt/splunkforwarder/etc
    rm -rf "/opt/splunkforwarder/etc.bak"

    # Delete autogenerated server.conf to make sure that when an instance is booted the servername and hostname get
    # set instead of mhcgeneric (set during phase 1 bake time)
    rm -f "/opt/splunkforwarder/etc/system/local/server.conf"
    `dirname $0`/initmunge.py --required-start "discoupdatecreds" /etc/init.d/splunk
    chkconfig splunk off
}
