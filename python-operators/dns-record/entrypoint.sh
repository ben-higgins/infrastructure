#!/usr/bin/env bash
set -x

python3 /scripts/dns-records.py \
  --envName ${ENVTYPE} \
  --region ${REGION} \
  --deployCloudfront ${DEPLOY_CLOUDFRONT} \
  --regionActingAs ${REGION_ACTING_AS}
