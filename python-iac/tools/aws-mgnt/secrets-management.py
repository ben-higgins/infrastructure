#!/usr/bin/python

import boto3
import json
import argparse
from botocore.exceptions import ClientError

parser = argparse.ArgumentParser()
parser.add_argument('--srcRegion', required=True, help='Secret manager source region')
parser.add_argument('--destRegion', help='Secrets manager destination region')
parser.add_argument('--srcEnvType', required=True, help='Source environment prefix name. Type "all" will copy all secrets')
parser.add_argument('--destEnvType', help='Destination environment prefix name')
parser.add_argument('--action', required=True, help='Action options: copy | delete')
args = parser.parse_args()

if args.srcRegion != args.destRegion and args.destRegion is not None:
    region = args.destRegion
    push_client = boto3.client('secretsmanager', region_name=args.destRegion)
    get_client = boto3.client('secretsmanager', region_name=args.srcRegion)
else:
    region = args.srcRegion
    get_client = boto3.client('secretsmanager', region_name=args.srcRegion)
    push_client = boto3.client('secretsmanager', region_name=args.srcRegion)

if args.srcEnvType == "all":
    filters = [{'Key': 'name','Values': ['develop','qa','main']}]
else:
    filters = [{'Key': 'name','Values': [args.srcEnvType]}]

# todo - fix MaxResults. should use NextToken instead
get_secrets_list = get_client.list_secrets(MaxResults=100,
                                           Filters=[filters])
secrets_list = get_secrets_list['SecretList']



for key in secrets_list:

    describe_secret = get_client.describe_secret(SecretId=key['Name'])
    try:
        secret_des = describe_secret['Description']
    except:
        secret_des = "Secrets for " + key['Name']

    get_secret_value = get_client.get_secret_value(SecretId=key['Name'])

    if args.srcEnvType != args.destEnvType and args.destEnvType is not None:
        stripEnv = key['Name'].split(args.srcEnvType,1)[1]
        secretName = args.destEnvType + stripEnv
    else:
        secretName = key['Name']


    if "copy" == args.action:
        try:
            print("Creating secret " + secretName + " in region " + region)
            create_secret_response = push_client.create_secret(
                Name=secretName,
                Description=secret_des,
                SecretString=get_secret_value['SecretString']
            )

        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print("error: ResourceNotFoundException")
            elif e.response['Error']['Code'] == 'InvalidParameterException':
                print("error: InvalidParameterException")
            elif e.response['Error']['Code'] == 'InvalidRequestException':
                print("error: InvalidParameterException")
            elif e.response['Error']['Code'] == 'InternalServiceError':
                print("error: InvalidParameterException")
            elif e.response['Error']['Code'] == 'ResourceExistsException':
                print("Secret already exists, syncing")
                try:
                    print("Updating secret: " + secretName)
                    update_secret_response = push_client.update_secret(
                        SecretId=secretName,
                        Description=secret_des,
                        SecretString=get_secret_value['SecretString']
                    )

                except ClientError as e:
                    if e.response['Error']['Code'] == 'ResourceNotFoundException':
                        print("error: ResourceNotFoundException")
                    elif e.response['Error']['Code'] == 'InvalidParameterException':
                        print("error: InvalidParameterException")
                    elif e.response['Error']['Code'] == 'InvalidRequestException':
                        print("error: InvalidParameterException")
                    elif e.response['Error']['Code'] == 'InternalServiceError':
                        print("error: InvalidParameterException")
                    else:
                        print(create_secret_response)
                else:
                    print("Updated successfully")
        else:
            print("Created successfully")
            print(create_secret_response['ARN'])



    elif "delete" == args.action:
        try:
            print("Deleting secret: " + secretName)
            delete_secret_response = get_client.delete_secret(
                SecretId=secretName,
                ForceDeleteWithoutRecovery=True
            )

        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print("error: ResourceNotFoundException")
            elif e.response['Error']['Code'] == 'InvalidParameterException':
                print("error: InvalidParameterException")
            elif e.response['Error']['Code'] == 'InvalidRequestException':
                print("error: InvalidParameterException")
            elif e.response['Error']['Code'] == 'InternalServiceError':
                print("error: InvalidParameterException")
        else:
            print("Deleted successfully")







