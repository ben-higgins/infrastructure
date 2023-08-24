#!/usr/bin/python3.8
"""
This tool will help switch from regular aws access to different eks deployments
Example: python3 change-credentials.py -e default -r eu-central-1
"""

import boto3
import argparse
import os
import subprocess

accessKey = ''
secretKey = ''

parser = argparse.ArgumentParser()
parser.add_argument("-e", required=True,
                help="environment name")
parser.add_argument("-r", help="eks deployed region")

args = parser.parse_args()
client = boto3.client('cloudformation',
                      region_name=args.r,
                      aws_access_key_id=accessKey,
                      aws_secret_access_key=secretKey)


def sub_process(command):
    # check if command is a string
    if isinstance(command, str):
        command = command.split()
    print(command)

    process = subprocess.Popen(command, stdout=subprocess.PIPE, universal_newlines=True)
    process.wait()

    output, error = process.communicate()
    if error is not None:
        return error
    else:
        return output


def get_cluster(branchName):
    #get stack name from cloudformation
    response = client.list_stacks(StackStatusFilter=[
        'CREATE_COMPLETE', 'ROLLBACK_FAILED', 'ROLLBACK_COMPLETE', 'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE'
    ])
    for key in response['StackSummaries']:
        if branchName + "-Eks" in key['StackName']:
            clusterName = key['StackName']
            print("EKS cluster name: " + clusterName)
            return clusterName


if args.e == "default":
    command = "aws-azure-login"
    sub_process(command)
    print("Personal access key restored")
    exit(0)

# get access key from cfn output
stackName = get_cluster(args.e)

if stackName is not None:
    response = client.describe_stacks(StackName=stackName)
    outputs = response["Stacks"][0]["Outputs"]
    f = open(os.environ["HOME"] + "/.aws/credentials", "w")
    for o in outputs:
        if o["OutputKey"] == "AccessKey":
            key1 = "aws_access_key_id = " + o["OutputValue"]
        if o["OutputKey"] == "AccessSecret":
            key2 = "aws_secret_access_key = " + o["OutputValue"]
        if o["OutputKey"] == "EKSConfig":
            command =o["OutputValue"]

    f.write("[default]\n" + key1 + "\n" + key2 + "\n")
    f.close()

    sub_process(command)
    print("local kubeconfig has been updated")
else:
    print("No stack found for " + args["envName"])

