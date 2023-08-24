#!/usr/bin/python

import argparse
import os

import lib.params as params
import lib.secrets_manager as secrets

parser = argparse.ArgumentParser()
parser.add_argument("--srcRegion", required=True, help="Secret manager source region")
parser.add_argument("--destRegion", help="Secrets manager destination region")
parser.add_argument(
    "--srcEnvName", required=True, help='Source environment prefix name. Type "all" will copy all secrets'
)
parser.add_argument("--destEnvName", help="Destination environment prefix name")
parser.add_argument("--action", required=True, help="Action options: copy | delete | build")
args = parser.parse_args()

if args.destRegion is None:
    params.load_params_mem(args.destEnvName)
    destRegion = os.environ["Region"]
else:
    destRegion = args.destRegion

# goal is if no secrets exists then create but if there are secrets do nothing
# if the action is build
if args.action == "build":
    # is the envName the same as one that already exist in the same region
    filter = [{"Key": "name", "Values": [args.destEnvName]}]
    existInRegion = secrets.get_all_secrets(destRegion, filter)
    count = 0
    for i in existInRegion:
        count = count + 1

    if count <= 5:
        filter = [{"Key": "name", "Values": [args.srcEnvName]}]
        secretsList = secrets.get_all_secrets(args.srcRegion, filter)
        for key in secretsList:
            secretDesc = secrets.get_secret_description(key["Name"], args.srcRegion)
            secretValue = secrets.get_json_secret_value(key["Name"], args.srcRegion)

            # change secrets envName if needed
            if args.srcEnvName != args.destEnvName and args.destEnvName is not None:
                stripEnv = key["Name"].split(args.srcEnvName, 1)[1]
                secretName = args.destEnvName + stripEnv
            else:
                secretName = key["Name"]

            secrets.create_secret(secretName, secretValue["SecretString"], secretDesc, destRegion)

    elif existInRegion:
        print("todo: update existing secrets")


elif args.action == "copy":

    # set filters to limit what is being retrieved
    if args.srcEnvName == "all":
        filters = [{"Key": "name", "Values": ["develop", "qa", "main"]}]
    else:
        filters = [{"Key": "name", "Values": [args.srcEnvName]}]

    # based on non-required args determine destination region
    if args.srcRegion != destRegion and destRegion is not None:
        region = destRegion
    else:
        region = args.srcRegion

    get_secrets_list = secrets.get_all_secrets(args.srcRegion, filters)

    for key in get_secrets_list:
        secretDesc = secrets.get_secret_description(args.srcEnvName, args.srcRegion)
        secretValue = secrets.get_json_secret_value(args.srcEnvName, args.srcRegion)

        # change secrets envName if needed
        if args.srcEnvName != args.destEnvName and args.destEnvName is not None:
            stripEnv = key["Name"].split(args.srcEnvName, 1)[1]
            secretName = args.destEnvName + stripEnv
        else:
            secretName = key["Name"]

        secrets.create_secret(secretName, secretValue, secretDesc, region)
