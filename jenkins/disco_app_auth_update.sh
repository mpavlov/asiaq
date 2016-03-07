#!/bin/bash -e

function print_help() {
    echo "usage: $0 <region> <env> [<path>]"
    echo
    echo "Updates environment specific application passwords"
    echo "Data is taken from <path>app_auth/<env>/".
    echo "If <path> is not specified. The script searches for ../app_auth relative to the script"
}

if [[ "$1" == "-h" || "$1" == "--help" || "$2" == "" ]] ; then
    print_help
    exit 1
fi

region="$1"
env="$2"
project="$(grep -i project_name disco_aws.ini | cut -d= -f 2)"

if [ "$3" != "" ]; then
    conf_dir="$3"
else
    conf_dir="$(dirname $0)/../"
fi;

bucket="${region}.${project}.credentials.${env}"

source "$(dirname $0)/boto_init.sh"

disco_app_auth.py --bucket $bucket --directory $conf_dir update
