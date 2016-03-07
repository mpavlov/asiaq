#! /bin/false #This file is for sourcing
# vim: ts=4 sw=4 et filetype=sh

function copy_require_plugin() {
    FROM_DIR=$1
    TO_DIR=$2
    PLUGIN=$3
    cp ${FROM_DIR}/${PLUGIN}/${PLUGIN}.hpi ${TO_DIR}/${PLUGIN}.hpi
    # jenkins want hpi under right permissions and ownership
    chown jenkins:sys ${TO_DIR}/${PLUGIN}.hpi
    chmod 664 ${TO_DIR}/${PLUGIN}.hpi
}
