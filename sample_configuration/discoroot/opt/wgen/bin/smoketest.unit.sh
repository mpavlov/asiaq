#! /bin/bash

# this script has to be crond safe. So we include all commands that we are using with absolute path
# the path should be updated if the linux distribution changes file locations.

# include verify_init_status and is_service_running

source $(dirname $0)/get_status.sh

HOSTCLASS=$(get_hostclass)
IFS=$'\n'
TESTS=($(get_smoketests))

checks=()

for TEST in ${TESTS[@]}
do
    IFS=$' '
    eval $TEST
    checks+=("$?")
done

# if any check fails. exit with non zero status code

exit_status=0

for check in ${checks[@]}
do
    exit_status=$((exit_status+1))
    if [[ "$check" -ne "0" ]]
    then
        >&2 echo "$HOSTCLASS is not running correctly"
        exit $exit_status
    fi
done

>&2 echo "$HOSTCLASS is running ok"
exit 0
