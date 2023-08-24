#!/usr/bin/python

import pysftp
import boto3
import base64
import os
import json
from botocore.exceptions import ClientError


def get_secret():

    secret_name = "dynata/sftp"
    region_name = "us-east-1"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )

    except ClientError as e:
        print(e)
    else:
        secret = get_secret_value_response['SecretString']
        return secret

secretStr = get_secret()
r = json.loads(secretStr)

s3_client = boto3.client('s3')

with pysftp.Connection(r['url'], username=r['username'], password=r['password']) as sftp:
    with sftp.cd('/RepTrakData'):
        flist  = sftp.listdir()
        for f in flist:
            p = 'tmp/' + f
            sftp.get(f, p, preserve_mtime=True)

            #upload to s3
            objectpath = 'NYSE/RAW_DATA/' + f
            try:
                response = s3_client.upload_file(p, 'ri-etl', objectpath)
            except ClientError as e:
                print(e)
            else:
                os.remove(p)
                # remove file from sftp site
