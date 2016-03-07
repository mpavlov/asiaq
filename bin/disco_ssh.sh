#!/bin/bash
set -e

SSH_OPTIONS="-oStrictHostKeyChecking=no -oUserKnownHostsFile=/dev/null"
JUMPBOX_HOSTNAME="mhcadminproxy"
LISTHOSTS_CACHE=  # will store the result of disco_aws.py listhosts so we don't have to fetch it from aws multiple times

function check_usage() {
    # print usage string on incorrect invocation
    if [[ -z "$1" ]] || [[ -z "$2" ]]; then
        echo "Usage: $0 <env> <hostname> [port1] [port2] [port3] ..." 1>&2
        exit 1
    fi
}

function get_hostnames_for_env() {
    # initializes LISTHOSTS_CACHE
    local env="$1"
    set -o pipefail
    set +e
    LISTHOSTS_CACHE=`disco_aws.py --env "$env" listhosts --hostname --private-ip | grep -v ' bake_'`
    if [ 0 -ne $? ]
    then
        echo 'Host listing failed -- are you on the VPN right now?'
        exit 1
    fi
    set +o pipefail
    set -e
}

function get_host_public_ip() {
    # return private ip address for a given hostname
    # if we just use hostclass as hostname, will return the first meet host
    local pattern="$1"
    echo -e "$LISTHOSTS_CACHE" | grep "$pattern" | awk 'NR==1 {print $3}'
}

function get_host_private_ip() {
    # return private ip address for a given hostname
    # if we just use hostclass as hostname, will return the first meet host
    local pattern="$1"
    echo -e "$LISTHOSTS_CACHE" | grep "$pattern" | awk 'NR==1 {print $5}'
}

function check_ip() {
    # exit if we got 0 ips, or more than 1 ip
    # NOTE: don't fold this into get_ip. get_ip is often invoked in a subshell, and 'exit 1' there won't do much
    local ip="$1"
    local hostname="$2"
    local env="$3"
    if [[ -z "$ip" ]] || [[ "$ip" == "-" ]]; then
        echo "Can't find host '$hostname' in env '$env'" 1>&2
        exit 1
    fi
    if [[ $(echo -e "$ip" | wc -l) -ne 1 ]]; then
        echo "Too many hosts match '$hostname'"
        exit 1
    fi
}

function activate_agent() {
    echo "INFO: Activating ssh-agent for this session"
    ssh-agent
    ssh-add ~/.ssh/id_rsa
}

function check_agent() {
    if [[ ! $(ssh-add -l | grep $USER) ]]; then
        activate_agent
    fi
    if [[ ! $(ssh-add -l | grep $USER) ]]; then
        echo "ERROR: SSH agent does not appear to be aware of your credentials."
        echo "See the README.rst for instructions on setting up SSH agent."
        exit 1
    fi
}

function do_ssh() {
    # ssh into a host
    local jumpbox_ip="$1"
    local host_ip="$2"

    # <experimental>
    # Normally, ssh doesn't allow a connection if the input doesn't come from the terminal.
    # But sometimes we may wish to redirect stdin from elsewhere and pretend it's the terminal.
    # This is enabled by passing -t (not once but twice!) to the ssh command.
    [[ ! -t 0 ]] && SSH_T="-t -t"
    # </experimental>
    local ssh_user=""
    [[ $SSH_USER != "" ]] && ssh_user="$SSH_USER@"
    cmd="ssh -At $SSH_T $SSH_OPTIONS ${ssh_user}${host_ip}"
    [[ "$jumpbox_ip" != "" ]] && cmd="ssh -At $SSH_T $SSH_OPTIONS $jumpbox_ip $cmd"

    echo "$cmd"
    $cmd
}

function do_tunnels() {
    # setup tunnels to a host
    local jumpbox_ip="$1"
    local host_ip="$2"
    local ports="$3"

    if [[ "$jumpbox_ip" == "" ]]; then
        echo "You're attempting to reach a public ip $host_ip. You don't need to tunnel."
        exit 1
    fi

    for port in $ports; do
        tunnel_args="$tunnel_args -L $port:$host_ip:$port"
    done
    cmd="ssh -A $tunnel_args $SSH_OPTIONS $jumpbox_ip"
    user_msg="echo -n 'Tunnel(s) created. Press Ctrl-C to disconnect...'"
    sleep_forever="tail -f /dev/null"
    echo "$cmd"
    $cmd "$user_msg; $sleep_forever"
}

function main() {
    check_usage $*

    env="$1" && shift
    host="$1" && shift
    ports="$*"

    get_hostnames_for_env "$env"

    # find jumpbox first
    jumpbox_ip=$(get_host_public_ip $JUMPBOX_HOSTNAME)

    # use public ip if we have no adminproxy
    if [[ "$jumpbox_ip" == "" ]]
    then
        host_ip=$(get_host_public_ip "$host")
    else
        host_ip=$(get_host_private_ip "$host")
    fi
    check_ip "$host_ip" "$host" "$env"

    check_agent

    if [[ "$ports" ]]; then
        do_tunnels "$jumpbox_ip" "$host_ip" "$ports"
    else
        do_ssh "$jumpbox_ip" "$host_ip"
    fi
}

echo "WARNING: disco_ssh.sh is deprecated. Please use disco_ssh.py"
main $*
