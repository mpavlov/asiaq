#!/bin/bash -e

function print_help() {
    echo "The first parameter is the name of the region in AWS to create the buckets in (us-west-1, us-east-1, etc.)"
    echo "The second parameter is the environment to create the buckets in (build, deploy, ci, prod, etc.)"
}

if [[ "$1" == "-h" || "$1" == "--help" || "$2" == "" ]] ; then
    print_help
    exit 1
fi

REGION="$1"
ENV="$2"
PROJECT="$(grep -i  project_name disco_aws.ini | cut -d= -f 2)"

BUCKET="$REGION.$PROJECT.credentials.$ENV"

source "$(dirname $0)/boto_init.sh"

pip install awscli > /dev/null

if [[ "$ENV" == "build" ]] ; then
    KEY_NAMES="bake"
elif [[ "$ENV" == "deploy" ]] ; then
    KEY_NAMES=""
else # ci prod and sandbox environments
    KEY_NAMES="test smoketest snapshot dashboard jenkins"
fi

TEMP_DIR="$(mktemp -d /tmp/tmp.XXXXXX)"
for NAME in $KEY_NAMES; do
    ssh-keygen -q -t rsa -b 2048 -P "" -C "$NAME" -f "$TEMP_DIR/$NAME"
    disco_creds.py --bucket $BUCKET set --key "private_keys/ssh/$NAME.key" \
        --value "$(cat $TEMP_DIR/$NAME)"
    disco_creds.py --bucket $BUCKET set --key "public_keys/ssh/$NAME.pub" \
        --value "$(cat $TEMP_DIR/$NAME.pub)"
    echo Generated new $NAME key
    if [[ "$NAME" == "bake" ]] ; then
        aws --region $REGION ec2 delete-key-pair --key-name "$NAME" > /dev/null
        aws --region $REGION ec2 import-key-pair --key-name "$NAME" \
            --public-key-material file://$TEMP_DIR/$NAME.pub > /dev/null
        echo Uploaded new $NAME key
    fi
done
rm -Rf $TEMP_DIR

# Keys that must be manually generated:
echo
echo Generate new SSL certs and keys, and
echo set these S3 keys with the appropriate SSL values:
echo

if [[ "$ENV" == "build" ]] ; then
    echo "  private_keys/ssl/jenkins/crt"
    echo "  private_keys/ssl/jenkins/key"
    echo "  private_keys/ad/bind_password"
    echo
elif [[ "$ENV" == "deploy" ]] ; then
    echo "  private_keys/ssl/deployenator/crt"
    echo "  private_keys/ssl/deployenator/key"
    echo "  private_keys/ad/bind_password"
elif [[ "$ENV" == "ci" ]] ; then
    echo "  private_keys/ssl/jenkins/crt"
    echo "  private_keys/ssl/jenkins/key"
    echo "  private_keys/ssl/deployenator/crt"
    echo "  private_keys/ssl/deployenator/key"
    echo "  private_keys/ad/bind_password"
else
    echo "  private_keys/ssl/adminproxy/crt"
    echo "  private_keys/ssl/adminproxy/key"
    echo "  private_keys/ad/bind_password"
fi

echo
echo These can be set using disco_creds.py:
echo   disco_creds.py --bucket $BUCKET set --key KEY_TO_SET --value VALUE_TO_SET
echo
