#!/bin/bash -e

function usage() {
  echo "Records the status of a job in a failure file"
  echo "Usage:  $0 job_name hostclass build_number success_status"
  exit 1
}

if [[ $# -ne 4 ]]; then
  usage
fi

JOB=$1
HOSTCLASS=$2
BUILD_NUMBER=$3
SUCCEEDED=$4
WORKSPACE=${WORKSPACE:-.}
FAILURE_FILE="$WORKSPACE/${HOSTCLASS}.failure"
BUILD_NUMBER_FILE="$WORKSPACE/${HOSTCLASS}.number"
LAST_BUILD=0
TRIGGERED_BY="triggered for $HOSTCLASS by build number $BUILD_NUMBER of source job"

if [[ -e $BUILD_NUMBER_FILE ]]; then
  LAST_BUILD=$(cat $BUILD_NUMBER_FILE)
fi

if [[ $BUILD_NUMBER -gt $LAST_BUILD ]]; then
  echo $BUILD_NUMBER > $BUILD_NUMBER_FILE
  if [[ ! $SUCCEEDED = "true" ]]; then
    echo "Recording failure for $JOB $TRIGGERED_BY"
    echo $BUILD_NUMBER > $FAILURE_FILE
  else
    echo "Recording success for $JOB $TRIGGERED_BY"
    rm -f $FAILURE_FILE
  fi
else
  if [[ $SUCCEEDED = "true" ]]; then
    echo "Received success for older $JOB $TRIGGERED_BY, discarding."
  else
    echo "Received failure for older $JOB $TRIGGERED_BY, discarding."
  fi
fi

FAILURES=$(echo $WORKSPACE/*.failure | sed -e "s|$WORKSPACE/||g" \
                                           -e "s|\.failure||g" \
                                           -e "s|\*||g")

if [[ -n $FAILURES ]]; then
  echo "There are extant failures for $JOB"
  echo "The following hostclasses are still failing:  $FAILURES"
  exit 1
else
  echo "$JOB looks good"
  exit 0
fi
