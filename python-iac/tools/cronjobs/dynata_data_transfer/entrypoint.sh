#!/bin/bash

if [[ -z "${AWS_ACCESS_KEY_ID}" ]]; then
  mkdir /root/.aws
  echo "[default]" > /root/.aws/credentials
  echo "${AWS_ACCESS_KEY_ID}" > /root/.aws/credentials
  echo "${AWS_SECRET_ACCESS_KEY}" > /root/.aws/credentials
  chmod 400 /root/.aws/credentials
fi

python /transfer.py