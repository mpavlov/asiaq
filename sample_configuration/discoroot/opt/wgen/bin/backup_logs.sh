#/bin/bash -xe

function print_help() {
    echo "This scripts backs up logs to S3 storage"
    echo "First parameter is the glob of the directories to sync, no trailing slash."
    echo "Rememer to single quote around glob to prevent shell expansion."
    echo "The second parameter is the glob of the files to move."
    echo "Remember to single quote around glob to prevent shell expansion."
}

if [[ "$1" == "" || "$2" == "" ]] ; then
    print_help
    exit 1
fi

DIRECTORY_GLOB="$1"
LOG_GLOB="$2-*"
HOSTCLASS=`cat /opt/wgen/etc/hostclass`

source "/opt/wgen/bin/user-data.sh" # pulls in 'environment_name'

# Expire after 1 year
EXPIRE_DATE=$(date -d "next year" --utc --rfc-3339=date)
OPTIONS="--expires=$EXPIRE_DATE --sse" # Also, use server side encryption
ZONE=$(curl --silent http://169.254.169.254/latest/meta-data/placement/availability-zone)
REGION=$(echo $ZONE | sed -e 's/.$//')
BUCKET="s3://$REGION.disco.logging.$environment_name"

# include http proxy to enable AWS client to run correctly

source "/etc/profile.d/proxy.sh"

for DIR in $DIRECTORY_GLOB ; do
    DEST_DIR=${BUCKET}/$(echo ${HOSTCLASS}/${DIR}/|tr -s '/')
    FILE_COUNT=$(ls $DIR/$LOG_GLOB 2>/dev/null | wc -w)
    if [[ "$FILE_COUNT" != "0" ]] ; then
        for FILE in $DIR/$LOG_GLOB ; do
            aws s3 mv $OPTIONS --region $REGION $FILE $DEST_DIR
        done
    fi
done
