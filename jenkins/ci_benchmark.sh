#! /bin/bash

source "$WORKSPACE/jenkins/boto_init.sh"

function date_to_utc() {
    echo $(date --utc --rfc-3339=seconds |sed 's/+00\:00/Z/;s/\ /T/')
}

if [ -z $FREQUENCY ]
then
    echo "FREQUENCY is required"
    exit 1
fi

if [ -z $DURATION ]
then
    echo "DURATION is required in seconds"
    exit 1
fi

# get all internal ip address to
ADMIN_PROXY=$(disco_aws.py --env ci listhosts --hostclass mhcadminproxy |awk '{print $3}')
DISCO_MQS=$(disco_aws.py --env ci listhosts --hostclass mhcdiscomq --hostname |awk '{print $4}')

STATS_END_POINT="disco_insight_service/student_profiling_tasks/stats.json"
LATENCY_OVER_TIME_END_POINT="disco_insight_service/student_profiling_tasks/stats.png"
LATENCY_HISTOGRAM_END_POINT="disco_insight_service/student_profiling_tasks/latency_histogram.png"
THROUGHTPUT_OVER_TIME_END_POINT="disco_insight_service/student_profiling_tasks/throughput_over_time.png"
TIMESTAMPS_END_POINT="disco_insight_service/student_profiling_tasks/timestamps.json"
LOAD_TEST_END_POINT="disco_sender_service/start_loadtest"

SENDER_SERVICE_PORT="1004"
INSIGHT_SERVICE_PORT="1005"

echo "admin proxy ip: " ${ADMIN_PROXY}
echo "list of disco mq: " ${DISCO_MQS}

echo '{"duration":"'$DURATION'", "frequency":"'$FREQUENCY'"}'

TIME_START=$(date_to_utc)

curl --insecure -X POST -H "Content-Type: application/json" --data '{"duration":"'$DURATION'", "frequency":"'$FREQUENCY'"}' "https://${ADMIN_PROXY}:${SENDER_SERVICE_PORT}/${LOAD_TEST_END_POINT}"

if [ "$?" != "0" ]
then
    echo "problem in network to access adminproxy"
    exit 1
fi

# sleep at least for the duration time to wait for benchmark finished
sleep $DURATION

# sleep another 2 seconds for last profile to finish, if it meets latency requirements
sleep 2
TIME_END=$(date_to_utc)

INSIGHT_TEMPLATE="time_start=$TIME_START&time_end=$TIME_END"

# sleep extra 5 mins before retrieve benchmark results
sleep 300

cd $WORKSPACE
cd ../builds/$BUILD_NUMBER

echo $(pwd)
# save artifacts

# get throughput
curl --insecure  "https://${ADMIN_PROXY}:${INSIGHT_SERVICE_PORT}/${THROUGHTPUT_OVER_TIME_END_POINT}?${INSIGHT_TEMPLATE}" > "throughput_over_time_${FREQUENCY}_Hz_${DURATION}_SECs.png"
# get latency histogram
curl --insecure  "https://${ADMIN_PROXY}:${INSIGHT_SERVICE_PORT}/${LATENCY_HISTOGRAM_END_POINT}?${INSIGHT_TEMPLATE}" > "latency_histogram_${FREQUENCY}_Hz_${DURATION}_SECs.png"
# get latency over time
curl --insecure  "https://${ADMIN_PROXY}:${INSIGHT_SERVICE_PORT}/${LATENCY_OVER_TIME_END_POINT}?${INSIGHT_TEMPLATE}" > "latency_over_time_${FREQUENCY}_Hz_${DURATION}_SECs.png"
# get stats json
curl --insecure  "https://${ADMIN_PROXY}:${INSIGHT_SERVICE_PORT}/${STATS_END_POINT}?${INSIGHT_TEMPLATE}" > "stats_${FREQUENCY}_Hz_${DURATION}_SECs.json"
# get timestamps json
curl --insecure  "https://${ADMIN_PROXY}:${INSIGHT_SERVICE_PORT}/${TIMESTAMPS_END_POINT}?${INSIGHT_TEMPLATE}" > "timestamps_${FREQUENCY}_Hz_${DURATION}_SECs.json"

# make sure workspace has the directory to display graphs
REPORT_DIR="${WORKSPACE}/_reports/${BUILD_NUMBER}"
mkdir -p $REPORT_DIR
cp *.json $REPORT_DIR
cp *.png $REPORT_DIR

# echo links to console log
cat <<DESCRIPTION

    stats_[frequency]_Hz_[duration]_SECs.json: Benchmark Results summary

    timestamps_[frequency]_Hz_[duration]_SECs.json: Profiling Task stats for every profiling task in the benchmark

    latency_histogram_[frequency]_Hz_[duration]_SECs.png: Histogram for latency distribution for profiling tasks

    latency_over_time_[frequency]_Hz_[duration]_SECs.png: Latency for profiling tasks during benchmark

    throughput_over_time_[frequency]_Hz_[duration]_SECs.png: Throughput for pipleine during benchmark
DESCRIPTION
cd $REPORT_DIR

for i in $(ls *.json; ls *.png)
do
    echo "${JOB_URL}ws/_reports/${BUILD_NUMBER}/${i}"
done

#check status, if no result, the ci-benchmark should fail so we fix stuff
outputfile="$WORKSPACE/../builds/$BUILD_NUMBER/stats_${FREQUENCY}_Hz_${DURATION}_SECs.json"
if ! grep '"complete_profile_count": 0,' "$outputfile" 
then
    echo "benchmark success"
    exit 0
else
    echo "no profile is completed. benchmark has failed"
    exit 1
fi
