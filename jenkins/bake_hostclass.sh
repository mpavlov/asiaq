#!/bin/bash

SELF_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
JENKINS_URL=https://localhost/jenkins/
JOB_NAME=bake-hostclass-STATUS
TOKEN="NjJmNmJkYTM5ZjBjMGE1OGM5MmE4OWNh"
SUCCEEDED="true"

echo "hostclass: $HOSTCLASS"

source "${SELF_DIR}/boto_init.sh"

disco_bake.py --debug bake --hostclass $HOSTCLASS --use-local-ip
if [[ "$?" != "0" ]] ; then SUCCEEDED="false" ; fi

curl -ksS -X POST $JENKINS_URL/job/$JOB_NAME/build --data token=$TOKEN \
    --data-urlencode json="{\"parameter\": [{\"name\":\"HOSTCLASS\", \"value\":\"$HOSTCLASS\"}, {\"name\":\"SUCCEEDED\", \"value\":\"$SUCCEEDED\"}]}"

if [[ "$SUCCEEDED" == "false" ]] ; then exit 1 ; fi
