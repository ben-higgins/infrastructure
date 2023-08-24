#!/usr/bin/python

import argparse
import boto3
import os
import lib.params as params

parser = argparse.ArgumentParser()

parser.add_argument("--region", help="Enviornment region")
parser.add_argument("--envName", required = True, help = "Required: Environment name equals environment to deploy to")
parser.add_argument("--branch", required = True, help = "Required: Git branch for deployment")

args = parser.parse_args()

def update_termination_protection(envName, branch, region):
    if branch == 'dr-main':
        print("")
        print("override branch is " + branch + " , so we can change the termination protection for " + envName)
        client = boto3.client('cloudformation', region_name = region)
        client.update_termination_protection(StackName = envName, EnableTerminationProtection=False)
    else:
        print("")
        print("override branch is " + branch + " , so we cannot change the termination protection for " + envName)


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
        update_termination_protection(args.envName, args.branch, region)
else:
    update_termination_protection(args.envName, args.branch, args.region)
