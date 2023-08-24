#!/bin/bash
set -x
env

python /scripts/replica-manager.py --env $ENVTYPE
