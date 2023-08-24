#!/usr/bin/python

import argparse
import boto3
import base64
import json
import yaml
import subprocess
import time
import docker
from botocore.exceptions import ClientError

ap = argparse.ArgumentParser()
ap.add_argument("--githubToken", required=False, choices=["True", "False"],
                help="For docker containers who pull assets from github during build")
ap.add_argument("--getSecrets", required=False, choices=["True", "False"],
                help="Retrieve only secrets from secrets manager")
ap.add_argument("--deployRegion", required=True,
                help="AWS region EKS was deployed to")
ap.add_argument("--jobName", required=True,
                help="Name of micro service/jenkins job being deployed")
ap.add_argument("--buildNumber", required=False,
                help="Container build number taken from Jenkins build number")
ap.add_argument("--branchName", required=True,
                help="Branch equals environment to deploy to")
ap.add_argument("--helmParams", required=False,
                help="List of additional params for helm")
args = vars(ap.parse_args())

def sub_process(command, action):
    if action == 1:
        process = subprocess.Popen(command.split(), stdout=subprocess.PIPE)
        process.wait()
        output, error = process.communicate()
        if error is not None:
            print(error)
            return error
        else:
            print(output)
            return output
    elif action == 2:
        process = subprocess.call(command.split())
        print(process)


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


def container_build(branchName, jobName, deployRegion, buildNumber, githubToken):
    # https://docker-py.readthedocs.io/en/stable/
    tag = jobName + ":" + branchName + "-" + buildNumber

    print("Step 3.a: Check if repository already exists in ECR")
    # confirm there's a repository in ecr
    client = boto3.client('ecr', region_name=deployRegion)
    response = client.describe_repositories()
    found = False
    for key in response["repositories"]:
        if jobName == key["repositoryName"]:
            found = True
    if  not found:
        print("ECR repository for " + jobName + " does not exist. Creating now")
        response = client.create_repository(
            repositoryName=jobName,
            encryptionConfiguration={
                'encryptionType': 'AES256'
            }
        )
        print(response)
    else:
        print("ECR Repository already exists in " + deployRegion)

    # connect to docker daemon
    try:
        docker_client = docker.from_env(version="auto")
    except:
        print("Error connecting to docker socket")
    else:
        docker_client = docker.DockerClient(base_url="unix://var/run/docker.sock", version="auto")

    print("Step 3.b: Build container")
    if githubToken and githubToken is not None:
        try:
            tokenList = json.loads(get_secret("github-token/react-components", deployRegion))
            image, build_log = docker_client.images.build(path='../' + jobName, tag=tag, rm=True, buildargs={'COMPOSER_AUTH': tokenList["COMPOSER_AUTH"]})
        except:
            print("Error Building container")
            print(build_log)
            exit(1)
    else:
        try:
            image, build_log = docker_client.images.build(path='../' + jobName, tag=tag, rm=True)
        except:
            print("Error Building container")
            print(build_log)
            exit(1)

    print(build_log)

    ecr_client = boto3.client('ecr', region_name=deployRegion)

    print("Step 3.c: ECR Authentication")
    ecr_credentials = (ecr_client
        .get_authorization_token()
    ['authorizationData'][0])

    ecr_username = 'AWS'
    ecr_password = (
        base64.b64decode(ecr_credentials['authorizationToken'])
            .replace(b'AWS:', b'')
            .decode('utf-8'))

    ecr_url = ecr_credentials['proxyEndpoint']

    # get Docker to login/authenticate with ECR
    docker_client.login(username=ecr_username, password=ecr_password, registry=ecr_url)

    # tag image for AWS ECR
    print("Step 3.d: Tag container image")
    ecr_repo_name = '{}/{}'.format(ecr_url.replace('https://', ''), tag)

    image.tag(ecr_repo_name)

    # push image to AWS ECR
    print("Step 3.e: Push container to ECR rep: " + ecr_repo_name)
    push_log = docker_client.images.push(ecr_repo_name)
    print(push_log)

    return ecr_repo_name

def get_secret(secret_name, deployRegion):
    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager',region_name=deployRegion)

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )

    except ClientError as e:
        raise e
    else:
        if 'SecretString' in get_secret_value_response:
            secret = get_secret_value_response['SecretString']
            return secret
        else:
            return base64.b64decode(get_secret_value_response['SecretBinary'])


def get_cluster(branchName, deployRegion):
    client = boto3.client('cloudformation', region_name=deployRegion)
    #get stack name from cloudformation
    response = client.list_stacks(StackStatusFilter=[
        'CREATE_COMPLETE', 'ROLLBACK_FAILED', 'ROLLBACK_COMPLETE', 'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE'
    ])
    for key in response['StackSummaries']:
        if branchName + "-Eks" in key['StackName']:
            clusterName = key['StackName']
            print("EKS cluster name: " + clusterName)
            return clusterName

def update_kubeconfig(clusterName, deployRegion):
    client = boto3.client('cloudformation', region_name=deployRegion)

    response = client.describe_stacks(StackName=clusterName)
    outputs = response["Stacks"][0]["Outputs"]
    for output in outputs:
        if output["OutputKey"] == "EKSConfig":
            print("updating local kube config file: " + output["OutputValue"])
            command = output["OutputValue"]
            sub_process(command, 2)
            time.sleep(10)

def create_configmap(branchName, jobName, deployRegion):
    secrets = json.loads(get_secret(branchName + "/" + jobName, deployRegion))

    setParams = ""
    for key in secrets:
        setParams = setParams + key + "=" + secrets[key] + "\n"


    configmapRaw = {"kind" : "ConfigMap",
                    "apiVersion" : "v1",
                    "metadata" :
                        {"name" : jobName + "-env" },
                    "data" :
                        { ".env" :
                              setParams }
                    }

    configmap = yaml.dump(configmapRaw)
    #import pdb; pdb.set_trace()
    f = open("jenkins/bin/configmap.yaml", "w")
    f.write(configmap.replace("'", ""))
    f.close()

    command = "kubectl apply -f jenkins/bin/configmap.yaml"
    sub_process(command, 2)

def deploy_helm(dockerContainer, jobName):
    #check if first revisioned failed
    command = "/usr/local/bin/helm history " + jobName + " --max 1 --output json"
    chartStatusRaw = sub_process(command, 1)

    try:
        chartJson = json.loads(chartStatusRaw)
    except:
        print("Deployment doesn't exist yet")

    else:
        if chartJson[0]['revision'] == 1:
            if chartJson[0]['status'] == "FAILED":
                command = "/usr/local/bin/helm delete " + jobName + " --purge"
                sub_process(command, 2)
                #make sure helm finishes deleting before moving on
                checkExists = sub_process(command, 1)

                while ("Error" in checkExists.decode()):
                    time.sleep(5)
                    checkExists = sub_process(command, 1)

    params = ""
    if args["helmParams"] is not None:
        paramList = args["helmParams"]
        for param in paramList.split():
            params = params + " --set " + param

    print(params)
    command = "/usr/local/bin/helm upgrade --install " + params + " --set container.image=" + dockerContainer + " --set serviceName=" + jobName + " --set volumeMount.name=" + jobName + "-env" + " --wait --timeout 300 " + jobName + " ../" + jobName +  "/.helm/deployment_chart"
    sub_process(command, 1)


#todo build logic to allow just retrieving secrets

#check overrides
print("Step 1: Select branch")
branchName = set_envtype(args["branchName"])

# build container
#build number is not required
print("Step 2: Build container")
if args["buildNumber"] is None:
    buildNumber = "1"
else:
    buildNumber = args["buildNumber"]

# some builds need a github key
if args['githubToken'] is not None or args['githubToken']:
    githubToken = True
else:
    githubToken = False

dockerContainer = container_build(branchName, args["jobName"], args["deployRegion"], buildNumber, githubToken)

# update-kubeconfig to connect to right cluster
print("Step 4: Get EKS Cluster Name")
clusterName = get_cluster(branchName, args["deployRegion"])

print("Step 5: Update kubectl config with EKS Cluster Details")
update_kubeconfig(clusterName, args["deployRegion"])

# create env configmap
print(f"Step 5: Create ENV configmap for branch {branchName}")
create_configmap(branchName, args["jobName"], args["deployRegion"])

# deploy helm charts
print("Step 7: Deploy helm chart")
deploy_helm(dockerContainer, args["jobName"])

#TODO
### for projects that don't copy application into container. Copy path varies
#echo ".env" >> .dockerignore
#sed 's/##COPYPLACEHOLDER##/COPY . \/application/g' Dockerfile


