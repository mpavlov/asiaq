#!/bin/bash -e

function print_help() {
    echo "usage: $0 <region> <env> [<dir>]"
    echo
    echo "Updates environment specific application passwords"
    echo "Data is taken from app_auth/<env>/"
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

disco_app_auth.py --bucket $bucket --directory $conf_dir update --force

# Print out the GENERATE_WHEN_EMPTY keys updated via --force
for FILE in $(find $conf_dir/app_auth/$env -type f) ; do
    set +e
    cat $FILE | grep -v GENERATE_WHEN_EMPTY > /dev/null
    FOUND="$?"
    set -e
    if [[ "$FOUND" == "1" ]] ; then
        # environment name is lower case a-z plus '-' since we allow 'vocab-prod' and 'burst-prod', 'sci-prod'
        # in future
        KEY_NAME=$(echo $FILE | grep -o "app_auth/.*" | sed -e 's.app_auth/[a-z\-]*/.app_auth/.')
        echo KEY $KEY_NAME
        echo VALUE $(disco_creds.py --bucket $bucket get --key $KEY_NAME)
    fi
done
