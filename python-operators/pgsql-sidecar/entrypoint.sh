#!/bin/bash
set -x
env

/usr/bin/python3.8 /scripts/db-management.py \
  -a ${ACTION} \
  -e ${ENVTYPE} \
  -r ${REGION} \
  -b ${BUCKET} \
  -s ${SERVICE_OVERRIDE}




