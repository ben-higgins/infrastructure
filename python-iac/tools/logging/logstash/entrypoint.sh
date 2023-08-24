#!/bin/bash

env
set -x

sed -i 's/##ES##/${ES}/g' /usr/share/logstash/config/logstash.conf
sed -i 's/##ENV##/${ENV}/g' /usr/share/logstash/config/logstash.conf
sed -i 's/##REGION##/${REGION}/g' /usr/share/logstash/config/logstash.conf

logstash
#/logstash-entrypoint.sh