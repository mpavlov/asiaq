#!/bin/bash

set -ex

function usage() {
    echo "Copy deployenator jobs config to local repo"
    echo "Usage $0 <hostname>"
    exit 1
}

function get_ip() {
    # return the ip address of build env deployenator server
    disco_aws.py --env build listhosts --hostname --private-ip | grep $1 | awk '{ if ($5 ~ /^10/) { print $5; } else { print "Invalid private IP", $5; exit 1 } }'
}

function get_repo_dir() {
    # Get the disco_aws_automation base dir
    cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd | sed 's/\(.*\)disco_aws_automation\(.*$\)/\1disco_aws_automation/'
}

function main() {
    if [ $# -ne 1 ]; then
        usage
    fi

    HOSTNAME=$1
    SERVER=$(get_ip $HOSTNAME)

    REPO_DIR=$(get_repo_dir)
    REMOTE_DIR="/opt/wgen/build/jenkins/jobs/"
    LOCAL_DIR="${REPO_DIR}/discoroot/opt/wgen/disco_deployenator/jobs/"

    # Only sync jobs config.xml, and delete the jobs in the /discoroot/opt/wgen/disco_deployenator/jobs local repo if doesn't exist in the deployenator server
    SSH_OPTIONS="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
    rsync -av -e "$SSH_OPTIONS" -m --delete --include='*/' --include='config.xml' --exclude='*' "$SERVER:${REMOTE_DIR}" "${LOCAL_DIR}"
}

main $*
