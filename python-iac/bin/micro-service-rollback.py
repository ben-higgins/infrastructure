import argparse
import boto3
import base64
import json
import yaml
import time
import docker
from botocore.exceptions import ClientError
import lib.params as param
import lib.secrets_manager as secrets
import lib.exec_ctl as exe


ap = argparse.ArgumentParser()
ap.add_argument("--deployRegion", required=False,
                help="AWS region EKS was deployed to")
ap.add_argument("--jobName", required=True,
                help="Name of micro service/jenkins job being deployed")
ap.add_argument("--branchName", required=True,
                help="Branch equals environment to deploy to")
args = vars(ap.parse_args())

def set_envtype(branch_raw):
    # value might come in with a prefix
    try:
        branch = branch_raw.split('/')[1]
    except:
        branch = branch_raw

    #TODO temporary workaround to assign an environment type of develop if deploying a feature branch
    if branch not in "develop qa main":
        envType = "develop"
    else:
        envType = branch

    return envType

def get_cluster(branchName, region):
    client = boto3.client('cloudformation', region_name=region)
    #get stack name from cloudformation
    response = client.list_stacks(StackStatusFilter=[
        'CREATE_COMPLETE', 'ROLLBACK_FAILED', 'ROLLBACK_COMPLETE', 'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE'
    ])

    if len(response['StackSummaries']) == 0:
        print("No cloudformation stack found in " + region + " region")
        exit(1)

    for key in response['StackSummaries']:
        if branchName + "-Eks" in key['StackName']:
            clusterName = key['StackName']
            print("EKS cluster name: " + clusterName)
            return clusterName

def update_kubeconfig(clusterName, region):
    client = boto3.client('cloudformation', region_name=region)

    response = client.describe_stacks(StackName=clusterName)
    outputs = response["Stacks"][0]["Outputs"]
    for output in outputs:
        if output["OutputKey"] == "EKSConfig":
            print("updating local kube config file: " + output["OutputValue"])
            command = output["OutputValue"]
            exe.sub_process(command.split())
            time.sleep(10)


def helm_rollback(jobName):
    #check if first revisioned failed
    command = "/usr/local/bin/helm rollback " + jobName + " 0"
    output = exe.sub_process(command.split())
    print(output)

# check overrides
print("Step 1: Select branch")
branchName = set_envtype(args["branchName"])

# set region
if args["deployRegion"] == "None":
    if branchName in "develop qa":
        region = "eu-west-1"
    elif branchName == "main":
        region = "eu-central-1"
else:
    region = args["deployRegion"]

#stop deployment if no region set
if not region:
    print("No region was supplied either through override or using branch based selection")
    exit(1)


print("Step 2: Get EKS Cluster Name")
clusterName = get_cluster(branchName, region)

# Exit the build if no EKS cluster is found
if not clusterName:
    print("No EKS cluster named " + branchName + " found in " + region + " region")
    exit(1)

# update-kubeconfig to connect to right cluster
print("Step 3: Update kubectl config with EKS Cluster Details")
update_kubeconfig(clusterName, region)

# deploy helm charts
print("Step 4: Rollback helm chart")
helm_rollback(args["jobName"])
