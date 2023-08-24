#!/usr/bin/python

import os
import requests
import boto3
import base64
from botocore.exceptions import ClientError
import json

envType = os.environ['ENV_TYPE']
regionName = os.environ['REGION_NAME']

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
        if e.response['Error']['Code'] == 'DecryptionFailureException':
            raise e
        elif e.response['Error']['Code'] == 'InternalServiceErrorException':
            raise e
        elif e.response['Error']['Code'] == 'InvalidParameterException':
            raise e
        elif e.response['Error']['Code'] == 'InvalidRequestException':
            raise e
        elif e.response['Error']['Code'] == 'ResourceNotFoundException':
            raise e
    else:
        # Decrypts secret using the associated KMS CMK.
        # Depending on whether the secret is a string or binary, one of these fields will be populated.
        if 'SecretString' in get_secret_value_response:
            secret = get_secret_value_response['SecretString']
            return secret
        else:
            decoded_binary_secret = base64.b64decode(get_secret_value_response['SecretBinary'])


# class
def get_header(vendor, envType):
    header = ''
    if vendor == 'airfox':
        # get client username, password, pin
        secretStr = get_secret("monitoring/airfox-client")

        r = json.loads(secretStr)
        email = r['email']
        passwd = r['password']
        pin = r['pin']

        # get firebase access key
        secretStr = get_secret("production/firebase")
        r = json.loads(secretStr)
        apiKey = r['firebase_api_key']

        # get token from firebase
        try:
            r = requests.post(url='https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword?key=' + apiKey,
                          data='{"email":"' + email + '","password":"' + passwd + '","returnSecureToken":true}')
        except:
            print('failed to connect to googleapi firebase')
        else:
            try:
                response = r.json()
                firebaseToken = response['idToken']
                userId = response['localId']
            except:
                print('No json returned. status: ' + str(r.status_code))

        payload = {'credentials': {'token': firebaseToken, 'user_id': userId}, 'device_id': 'en28an3135dkgeas'}

        # get JWT token from airfox
        try:
            r = requests.post(url='https://airfox-api-gateway.mgensuite.com/api/user/v1/auth/login',
                          json=payload,
                          headers={'Content-Type': 'application/json', 'airfox-app-version': '2'})
            response = r.json()
            accesToken = response['data']['access_token']
            foxId = response['data']['fox_id']

        except:
            print('failed to connect and retrieve JWT token')
            print(r.text)

        header = {'Content-Type': 'application/json',
              'Authorization': accesToken}

    elif vendor == 'qiwi':
        secretStr = get_secret("production/qiwi")
        r = json.loads(secretStr)
        user = r['headers']['user_login']
        pwd = r['headers']['user_pass']

        header = {'Content-Type': 'application/json', 'user_login': str(user), 'user_pass': str(pwd)}
        foxId = ""
    elif vendor == 'fastcash':
        header = ""
        foxId = ""
    else:
        header = ""
        foxId = ""

    print(header)
    return header, foxId


