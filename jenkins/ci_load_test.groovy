// You need to copy and paste the whole script to the ci-load-test jenkins job
// Requiremnts:
// 1. ci-load-test has to be a jenkins build flow
// 2. there exists ci-benchmark job
// 3. ci-benchmark job takes FREQUENCY and DURATION arguments
// Any changes will break this script, and please update this script to reflect the
// reality

def frequencies = [1, 5, 10, 15, 20, 25, 30, 35, 40, 45]
frequencies.each { freq ->
    build("ci-benchmark", "FREQUENCY": freq.toString(), "DURATION": 600.toString())
}
