#!/usr/bin/python

import argparse
import lib.secrets_manager as secrets
import lib.params as params
import os
from distutils import util

parser = argparse.ArgumentParser()
parser.add_argument('--region', help='Secrets manager destination region')
parser.add_argument('--envName', help='Destination environment prefix name')
parser.add_argument('--delCFSecrets', help='Delete Secrets created by Cloudformation')
args = parser.parse_args()

def deleteSecrets(envName, region, filters):
    print("")
    print("Removing secrets of " + envName + " env in " + region + " region")
    get_secrets_list = secrets.get_all_secrets(region, filters)

    for key in get_secrets_list:
        print(key['SecretList'][0]['Name'])
        secrets.delete_secret(key['SecretList'][0]['Name'], region)

if args.delCFSecrets is None:
    delCloudformationSecrets = False
else:
    # Converting string argument to type boolean
    delCloudformationSecrets = bool(util.strtobool(args.delCFSecrets))

if delCloudformationSecrets is True:
    filters = [{'Key': 'name','Values': [args.envName]}]
else:
    filters = [{'Key': 'name','Values': [args.envName]}, {'Key': 'tag-key','Values': ['!aws:cloudformation:stack-id']}]

if args.region is None:
    # Create a list of all regions of the env
    paramsDir = "./params/" + args.envName + "/"
    regions = [ name for name in os.listdir(paramsDir) if os.path.isdir(os.path.join(paramsDir, name)) ]
    print("")
    print("For " + args.envName + " env, selected regions are " + ", ".join(regions))

    # Loop through the list of regions and perform the selected action on every region
    for region in regions:
        # load params into memory
        params.load_params_mem(args.envName, region)
        region = os.environ["Region"]
        deleteSecrets(args.envName, region, filters)

else:
    region = args.region
    deleteSecrets(args.envName, region, filters)
