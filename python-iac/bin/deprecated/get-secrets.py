#!/usr/bin/python

import boto3
import sys
import os
import base64
import json
from botocore.exceptions import ClientError

if len(sys.argv) == 1:
    print("No arguments passed")
    exit(1)

envType = sys.argv[1]
regionName = sys.argv[2]
serviceName = sys.argv[3]
path = envType + "/" + serviceName

session = boto3.session.Session()
client = session.client(
    service_name='secretsmanager',
    region_name=regionName)

# get secrets from aws secrets manager
def get_secret(secret_name):
    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )

    except ClientError as e:
        raise e
    else:
        # Decrypts secret using the associated KMS CMK.
        # Depending on whether the secret is a string or binary, one of these fields will be populated.
        if 'SecretString' in get_secret_value_response:
            secret = get_secret_value_response['SecretString']
            return secret
        else:
            decoded_binary_secret = base64.b64decode(get_secret_value_response['SecretBinary'])


secrets = json.loads(get_secret(path))

setParams = ""
for key in secrets:
    value = secrets[key]
    setParams = setParams + "" + key + "=" + value + "\n"

print(setParams)
