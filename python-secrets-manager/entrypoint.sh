#!/usr/bin/env bash
ls -l
ls -l ./secrets_encrypted
python /scripts/secrets-manager.py \
  --app ${APP} \
  --env null \
  --action ${ACTION}