#!/bin/bash -e

function print_help() {
    echo "usage: $0 <pipeline_definition>"
}

if [[ "$1" == "-h" || "$1" == "--help" || "$1" == "" ]] ; then
    print_help
    exit 1
fi

RUN_DIR=$PWD
SELF_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
PIPELINE_DEF="$1"

source "$(dirname $0)/boto_init.sh"

PIPE_HC=`awk -F, '/^[0-9]/{print $2}' $PIPELINE_DEF | sort -u`

echo "Hosts we will bake"
echo $PIPE_HC
echo

TMP_DIR=$(mktemp -d "$BASE_DIR/tmp.XXXXXXXXX")

PIDS=""
for HC in $PIPE_HC; do
    echo "Starting bake of $HC"
    disco_bake.py --debug bake --hostclass $HC &> $TMP_DIR/$HC.log &
    sleep 20 #slow down how many bakes happen at once.
    PID="$!"
    PIDS="$PIDS $PID"
    echo $HC > "$TMP_DIR/$PID.is"
done

SUCCESS_PIDS=""
FAIL_PIDS=""
for PID in $PIDS; do
    if wait $PID ; then
        SUCCESS_PIDS="$SUCCESS_PIDS $PID"
    else
        FAIL_PIDS="$FAIL_PIDS $PID"
    fi
done

for PID in $SUCCESS_PIDS; do
    HC=$(cat $TMP_DIR/$PID.is)
    echo "Successfully Baked $HC"
    grep Created $TMP_DIR/$HC.log | grep AMI
    echo "----------------------"
    echo
done

for PID in $FAIL_PIDS; do
    HC=$(cat $TMP_DIR/$PID.is)
    echo "Failed to Bake $HC"
    cat $TMP_DIR/$HC.log
    echo "----------------------"
    echo
done

OUT_CSV=$(mktemp "XXXX.csv")
pushd $SELF_DIR
  echo "ami_map = {}" > ami_map.py
  grep Created $TMP_DIR/*.log | awk '{ print "ami_map[\"" $2 "\"]=\"" $5 "\"" }' >> ami_map.py
  $SELF_DIR/add_ami_to_pipeline_csv.py --input $RUN_DIR/$PIPELINE_DEF --output $RUN_DIR/$OUT_CSV
  rm ami_map.py
popd
echo Created pipeline definition with new AMIs specified: $OUT_CSV

if [[ "$FAIL_PIDS" != "" ]] ; then
    exit 1
fi

rm -Rf $TMP_DIR

echo "Baked all hostclasses successfully."
