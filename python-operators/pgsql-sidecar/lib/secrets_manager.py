import boto3
import base64
from botocore.exceptions import ClientError

def get_secret(secret_name, region):
    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager',region_name=region)

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )

    except ClientError as e:
        return None
    else:
        if 'SecretString' in get_secret_value_response:
            secret = get_secret_value_response['SecretString']
            return secret
        else:
            return base64.b64decode(get_secret_value_response['SecretBinary'])

def get_all_secrets(filters, region):
    client = boto3.client(service_name='secretsmanager', region_name=region)
    response = client.list_secrets(MaxResults=100, Filters=[filters])
    return response['SecretList']

def create_secret(secretName, secretString, secretDesc, region):
    push_client = boto3.client('secretsmanager', region_name=region)
    try:
        print("Creating secret " + secretName + " in region " + region)
        create_secret_response = push_client.create_secret(
            Name=secretName,
            Description=secretDesc,
            SecretString=secretString
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
                    Description=secretDesc,
                    SecretString=secretString
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
                    print(update_secret_response)
            else:
                print("Updated successfully")
    else:
        print("Created successfully")
        print(create_secret_response['ARN'])


def get_secret_description(secretName, region):
    get_client = boto3.client('secretsmanager', region_name=region)
    describe_secret = get_client.describe_secret(SecretId=secretName)
    try:
        secret_desc = describe_secret['Description']
    except:
        secret_desc = "Secrets for " + secretName

    return secret_desc

def get_json_secret_value(secretName, region):
    get_client = boto3.client('secretsmanager', region_name=region)
    try:
        get_secret_value = get_client.get_secret_value(SecretId=secretName)
    except:
        get_secret_value = None

    return get_secret_value

def delete_secret(secretName, region):
    client = boto3.client('secretsmanager', region_name=region)
    try:
        print("Deleting secret: " + secretName)
        client.delete_secret(
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
