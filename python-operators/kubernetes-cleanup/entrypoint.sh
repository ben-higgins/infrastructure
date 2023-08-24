#!/usr/bin/env bash
set -x

python3 /scripts/kubernetes-cleanup.py \
  --envName ${ENVTYPE} \
  --region ${REGION} \
  --secret ${SECRET_NAME}
