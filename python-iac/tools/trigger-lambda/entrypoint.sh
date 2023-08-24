#!/usr/bin/env bash
set -x

python3 /scripts/trigger-lambda.py \
-e ${ENVTYPE} \
-r ${REGION} \
-a ${ACTION} \
-d ${DNS_ENTRY}
