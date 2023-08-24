#!/usr/bin/python
""" Handles the translation and insertion of secrets from github
into secrets manager.
TODO:
- Add support for multi files to ease github tracking. e.g.:
    * platform-api/dev/auth0url
    * platform-api/dev/auth0User
"""
import argparse
import boto3
import datetime
import logging
import os
import textwrap
import aws_encryption_sdk
from lib.secrets_manager import create_secret
from lib.region_manager import RegionManager


parser = argparse.ArgumentParser()

parser.add_argument(
    '--region',
    help='Secret manager source region'
)
parser.add_argument(
    '--branch_name',
    help='Git project branch name'
)
parser.add_argument(
    '--environment',
    help='Environment where the deployment is expected'
)
parser.add_argument(
    '--secrets_directory',
    default='secrets_encrypted',
    help='Directory where the encrypted secrets are stored'
)
parser.add_argument(
    '--app',
    required=True,
    help=(
        """App name, required to construct the secret name.
        e.g.: platform-api/dev, platform-filters/production
        """
    )
)
parser.add_argument(
    '--kms_key_arn',
    required=False,
    help='KMS key arn. This is used for edge cases only'
)

# set global variables
args = parser.parse_args()
boto_client = boto3.client('kms', region_name="us-east-1")
client = aws_encryption_sdk.EncryptionSDKClient()

secrets_file = ''

# if there's no secrets directory then exit
if not os.path.exists(args.secrets_directory):
    logging.warning(
        textwrap.dedent(
            f"No secrets directory found. Skipping secrets push to aws secrets manager."
        )
    )
    exit(0)


# first check if we are overriding
if args.environment != '':
    env = args.environment
    print(f'Overriding environment and sending secrets to {env}')

    # check if there are secrets for env
    for file in os.listdir(args.secrets_directory):
        if env in file:
            secrets_file = file

else:
    env = args.branch_name
    print(f'Sending secrets to the environment that matches branch name: {env}')
    for file in os.listdir(args.secrets_directory):
        if env in file:
            secrets_file = file


## end global variables

def create_key(name):
    response = boto_client.create_key(
        Description=name,
        KeyUsage='ENCRYPT_DECRYPT',
        Origin='AWS_KMS',
        Tags=[
            {
                'TagKey': 'Name',
                'TagValue': name
            },
            {
                'TagKey': 'Environment',
                'TagValue': env
            }
        ]
    )

    return response['KeyMetadata']['Arn']

def retrieve_key():
    response = boto_client.list_keys()
    return response['Keys']

def get_kms_arn(app):
    # search for the arn
    for keyid in retrieve_key():
        response = boto_client.describe_key(KeyId=keyid['KeyId'])
        if app in response['KeyMetadata']['Description']:
            arn = response['KeyMetadata']['Arn']

    try:
        return arn
    except NameError:
        arn = ""
        return arn

def decrypt_file(path: str, keys_arn: list) -> str:

    kms_key_provider = aws_encryption_sdk.StrictAwsKmsMasterKeyProvider(
        key_ids=keys_arn
    )
    response = '{}'

    with open(path, "rb") as file:
        file_content = file.read()

        response = client.decrypt(
            source=file_content,
            key_provider=kms_key_provider,
        )

        if len(response):
            response = response[0].decode()
        else:
            exit(1) # failed to decrypt so exit

    print(f'File decrypted with: {keys_arn}')
    return response


def get_secret_dict(path: str, key_arn: str) -> str:

    if not os.path.isfile(path):

        logging.warning(
            textwrap.dedent(
                f"""We only support secret files.
                    {path} is a folder.
                """
            )
        )
        exit(1)

    decrypted_data = decrypt_file(path, keys_arn=[key_arn])
    return decrypted_data


def push_secrets_to_aws(secrets_file):

    if os.path.isdir(f'{args.secrets_directory}/{env}'):
        # use file name as secret name for files within env folder

        for file in os.listdir(f'{args.secrets_directory}/{env}'):

            secrets_full_path = (
                f'{args.secrets_directory}/{env}/{file}'
            )

            print('Secret folder location: ', secrets_full_path)

            kms_key_arn = get_kms_arn(args.app)
            # Construct dict as app/env{...}
            secret_data = get_secret_dict(
                path=secrets_full_path,
                key_arn=kms_key_arn,
            )

            secretName = os.path.splitext(file)[0]

            create_secret(
                secretName=f'{env}/{secretName}',
                secretDesc=f'updated at {datetime.datetime.now()}',
                secretString=secret_data,
                region=args.region,
            )

    else:

        # if we don't have secrets check for branch named secrets
        if secrets_file == '':
            if env != args.branch_name:
                for file in os.listdir(args.secrets_directory):
                    if args.branch_name in file:
                        secrets_file = file

        # if still empty default to develop
        if secrets_file == '':
            for file in os.listdir(args.secrets_directory):
                if 'develop' in file:
                    secrets_file = file

        secrets_full_path = (
            f'{args.secrets_directory}/{secrets_file}'
        )

        print('Secret folder location: ', secrets_full_path)

        # Construct dict as app/env{...}
        try:
            kms_key_arn = get_kms_arn(args.app)
            secret_data = get_secret_dict(
                path=secrets_full_path,
                key_arn=kms_key_arn,
            )
        except:
            print(f'\nFailed to decrypting files with key: {kms_key_arn}\nTrying with passed in param\n')
            try:
                kms_key_arn = args.kms_key_arn
                secret_data = get_secret_dict(
                    path=secrets_full_path,
                    key_arn=kms_key_arn,
                )
            except:
                print(f'\nFailed to decrypt files using {kms_key_arn}\nGiving up and exiting script\n')
                exit(1)

        create_secret(
            secretName=f'{env}/{args.app}',
            secretDesc=f'updated at {datetime.datetime.now()}',
            secretString=secret_data,
            region=args.region,
        )

    return "Pushed secrets to AWS"

if __name__ == '__main__':

    for region in RegionManager.get_regions(
        environment=env,
        region=args.region
    ):
        args.region = region
        push_secrets_to_aws(secrets_file)
