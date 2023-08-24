#!/usr/bin/python

import boto3
import os
import base64
import json
from botocore.exceptions import ClientError
import argparse

ap = argparse.ArgumentParser()
ap.add_argument("--env-type", required=True)
ap.add_argument("--region-name", required=True)
ap.add_argument("--service-name", required=True)

args = vars(ap.parse_args())

envType = args["env-type"]
regionName = args["region-name"]
serviceName = args["service-name"]
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
        # Depending on whether the secret is a string or binary,
        # one of these fields will be populated.
        if 'SecretString' in get_secret_value_response:
            secret = get_secret_value_response['SecretString']
            return secret
        else:
            return base64.b64decode(get_secret_value_response['SecretBinary'])


secrets = json.loads(get_secret(path))

setParams = ""
for key in secrets:
    value = secrets[key]
    setParams = setParams + "    " + key + "=" + value + "\n"

print(setParams)
