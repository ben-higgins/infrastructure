
import argparse
import boto3
import json
from pprint import pprint
from subprocess import Popen, PIPE
from lib.cloudformation_manager import CloudformationManager
import logging
import botocore

parser = argparse.ArgumentParser()
parser.add_argument("-e", required=True, help="environment name")
parser.add_argument("-r", required=True, help="eks deployed region")
parser.add_argument("-a", required=True, help="lambda action for cloudformation")
parser.add_argument("-d", required=True, help="dns entry for microservice")

args = parser.parse_args()

region = args.r
environment = args.e
action = args.a
dnsName = args.d

def fetch_lambda_arn(envName, region):
    try:
        waf_cluster_name = CloudformationManager.get_service_stack_name(region, envName, "CloudfrontLambda")
        cluster_name = waf_cluster_name
    except Exception:
        cluster_name = ""
        logging.info(f"Error getting CloudfrontLambda cluster")

    outputs = CloudformationManager.get_stack_outputs(region, cluster_name)

    for output in outputs:
        if output["OutputKey"] == "CreateCFLambdaARN":
            return output["OutputValue"]

    raise Exception(f"CreateCFLambdaARN not found in region {region} for env {envName}")

def trigger_the_lambda(region, lambdaName, action, dnsName, dnsFqdnEntry):
    # https://stackoverflow.com/a/62563412
    # https://aws.amazon.com/premiumsupport/knowledge-center/lambda-function-retry-timeout-sdk/
    # https://botocore.amazonaws.com/v1/documentation/api/latest/reference/config.html
    cfg = botocore.config.Config(retries={'max_attempts': 0}, read_timeout=950, region_name=region)
    client = boto3.client('lambda', config=cfg, region_name=region)
    arguments = {
        'action': action,
        'dnsName': dnsName,
        'dnsFqdnEntry': dnsFqdnEntry
    }
    response = client.invoke(
                    FunctionName=lambdaName,
                    InvocationType='RequestResponse',
                    LogType='None',
                    Payload=json.dumps(arguments)
                )
    if 'FunctionError' in response.keys():
        print(f"stack's deployment failed")
        return False

    stackStatus = json.loads(response['Payload'].read().decode('utf-8'))['StackActionStatus']
    lambdaStatusCode = response['StatusCode']

    if stackStatus == "Failed" and lambdaStatusCode != "200":
        return False
    else:
        return True

def construct_dns_entry(dnsName, envName, region):

    # Decide about the dns entry domain, prefix part and dns entry type
    if envName == "main" and (region == "eu-central-1" or region == "us-east-1" or region == "ap-southeast-2"):
        dnsEnvPrefix = ""
        dnsEntryZone = "reptrak.com"
    elif envName == "qa" and region == "eu-west-1":
        dnsEnvPrefix = envName + "-"
        dnsEntryZone = "reptrak.io"
    elif envName == "develop" and region == "eu-west-1":
        dnsEnvPrefix = envName + "-"
        dnsEntryZone = "reptrak.io"
    elif envName == "testing" and (region == "eu-west-1" or region == "us-east-1"):
        dnsEnvPrefix = envName + "-"
        dnsEntryZone = "reptrak.io"
    elif region == "eu-west-1" or region == "us-east-1":
        dnsEnvPrefix = envName + "-"
        dnsEntryZone = "reptrak.io"
    else:
        dnsEntryZone = None
        dnsEnvPrefix = None

    if dnsName is not None and dnsEntryZone is not None:
        dnsEntryName = dnsEnvPrefix + dnsName + "." + dnsEntryZone
    else:
        print(f"Failed to construct the DNS entry")
        dnsEntryName = None

    return dnsEntryName

print(f"region is {region}")
print(f"environment is {environment}")
print(f"action is {action}")
print(f"dnsName is {dnsName}")
lambdaName = fetch_lambda_arn(environment, region)
print(f"lambdaName is {lambdaName}")
dnsFqdnEntry = construct_dns_entry(dnsName, environment, region)
print(f"dnsFqdnEntry is {dnsFqdnEntry}")

stackDeployed = trigger_the_lambda(region, lambdaName, action, dnsName, dnsFqdnEntry)
if (stackDeployed):
    print(f"Cloudfront stack {action} action completed successfully")
else:
    print(f"Cloudfront stack {action} action failed")
    exit(1)
