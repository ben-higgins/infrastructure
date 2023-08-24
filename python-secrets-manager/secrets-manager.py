 # source https://aws.amazon.com/blogs/security/new-aws-encryption-sdk-for-python-simplifies-multiple-master-key-encryption/
import aws_encryption_sdk
import boto3
import argparse
import os
import glob
import json
import pipes


ap = argparse.ArgumentParser()
ap.add_argument("--action", required=True, choices=["encrypt", "decrypt", "local", "local_json"])
ap.add_argument("--app", required=True)
ap.add_argument("--env", required=True)
ap.add_argument("--secrets_directory", required=False, default="secrets_encrypted")
args = ap.parse_args()

# depricating --app arg and getting the value from parent
p = os.path.abspath('.')
app = os.path.basename(p)

crypto_client = aws_encryption_sdk.EncryptionSDKClient()
boto_client = boto3.client('kms', region_name="us-east-1")

def validateJSON(filepath):
    text = open(filepath, "r")
    try:
        json.load(text)
    except ValueError as err:
        return False
    return True

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
                'TagValue': args.env
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
        arn = create_key(app)
        return arn

def decrypt_file(path: str, filePath: str, fileName: str) -> str:

    keyArn = get_kms_arn(app)
    kms_key_provider = aws_encryption_sdk.StrictAwsKmsMasterKeyProvider(
        key_ids=[keyArn]
    )

    base = os.path.splitext(fileName)[0]
    with open(filePath, 'rb') as infile, open(f'{path}/{base}.json', 'wb') as outfile:
        with crypto_client.stream(
            mode='d',
            source=infile,
            key_provider=kms_key_provider
        ) as decryptor:
            for chunk in decryptor:
                outfile.write(chunk)

    # cleanup
    os.remove(filePath)
    return f'Decrypted file {fileName}'


def encrypt_file(path: str, filePath: str, fileName: str) -> str:
    # validate json format
    if not validateJSON(filePath):
        print(f'Json format is malformed. Check file {fileName} for errors')
        exit(1)

    keyArn = get_kms_arn(app)
    kms_key_provider = aws_encryption_sdk.StrictAwsKmsMasterKeyProvider(
        key_ids=[keyArn]
    )

    # Open the files for reading and writing
    base = os.path.splitext(fileName)[0]
    with open(filePath, 'rb') as infile, open(f'{path}/{base}.encrypted', 'wb') as outfile:
        # Encrypt the file
        with crypto_client.stream(
                mode='e',
                source=infile,
                key_provider=kms_key_provider
        ) as encryptor:
            for chunk in encryptor:
                outfile.write(chunk)

    # cleanup
    os.remove(filePath)
    return f'Encrypted file {fileName}'


def develop_print(filename):
    response = open(filename, "r")
    print("\n")
    #newsecrets = f'# secrets generated from {filename}\n'
    for k, v in json.load(response).items():
        k = k.strip()
        v = v.strip()
        #newsecrets = newsecrets + f'{k}={v}\n'
        print("%s=%s" % (k, v))

    print("\n### Copy and paste the above output into your local .env file ###\n")


def json_print():
    print("\n")

    env_vars = {}  # or dict {}
    with open("./.env") as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue

            key, value = line.strip().split('=', 1)
            env_vars[key.strip()] = value.strip()

    print(json.dumps(env_vars, indent=2))
    print("\n### Copy and paste the above output into your ./secrets_encrypted/local.json file then run make encrypt ###\n")

if args.action == "encrypt":
    if os.path.isdir(f'{args.secrets_directory}/{args.env}'):
        list = glob.glob(f'{args.secrets_directory}/{args.env}/*.json')
        for file in list:
            base=os.path.basename(file)
            response = encrypt_file(f'{args.secrets_directory}/{args.env}', file, base)
            print(response)
    else:
        list = glob.glob(f'{args.secrets_directory}/*.json')
        for file in list:
            base=os.path.basename(file)
            response = encrypt_file(f'{args.secrets_directory}', file, base)
            print(response)

elif args.action == "decrypt":
    if os.path.isdir(f'{args.secrets_directory}/{args.env}'):
        list = glob.glob(f'{args.secrets_directory}/{args.env}/*.encrypted')
        for file in list:
            base=os.path.basename(file)
            response = decrypt_file(f'{args.secrets_directory}/{args.env}', file, base)
            print(response)
    else:
        list = glob.glob(f'{args.secrets_directory}/*.encrypted')
        for file in list:
            base=os.path.basename(file)
            response = decrypt_file(f'{args.secrets_directory}', file, base)
            print(response)
elif args.action == "local":
    # try if file has already been decrypted
    try:
        develop_print(f'./{args.secrets_directory}/local.json')
    except:
        list = glob.glob(f'{args.secrets_directory}/*.encrypted')
        if len(list) != 0:
            for file in list:
                base=os.path.basename(file)
                # only allowing building local environment from develop secrets for now
                if "local" in base:
                    response = decrypt_file(f'{args.secrets_directory}', file, base)
                    print(response)

                    # extract json to .env
                    develop_print(f'./{args.secrets_directory}/local.json')

elif args.action == "local_json":
    json_print()
