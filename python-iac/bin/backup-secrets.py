#!/usr/bin/python

import argparse
import lib.secrets_manager as secrets
import os
import json
from datetime import datetime
import lib.kms as kms
import shutil

# https://gitpython.readthedocs.io/en/stable/intro.html
# https://gitpython.readthedocs.io/en/stable/tutorial.html
from git import Repo

parser = argparse.ArgumentParser()
parser.add_argument('--region', required=True, help='Secret manager region')
parser.add_argument('--envName', required=True,
                    help='Environment prefix name. Type "all" will copy all secrets')
args = parser.parse_args()

CMK = "arn:aws:kms:eu-central-1:663946581577:key/937a0e30-645f-4576-b6b2-0899e812fadc"
repoURL = "git@github.com:RepTrak/devops-secretsmanager.git"
repoPath = "devops-secretsmanager"

# If we have to backup all secrets, then we need to call get_all_secrets() without the filters
if args.envName == "all":
    get_secrets_list = secrets.get_all_secrets(args.region)
else:
    filters = [{'Key': 'name', 'Values': [args.envName]}]
    get_secrets_list = secrets.get_all_secrets(args.region, filters)

# Clone the repo in a local path
repo = Repo.clone_from(repoURL, repoPath)

# Loop through the list of secrets and backup them
secretTotal = len(get_secrets_list)
secretIndex = 1
for key in get_secrets_list:
    secretName = key['SecretList'][0]['Name']

    print("Taking backup of Secret " + str(secretIndex) + "/" + str(secretTotal) +  " (" + args.region + "): " + secretName)
    secretIndex +=1

    secretDesc = secrets.get_secret_description(secretName, args.region)
    secretValue = secrets.get_json_secret_value(secretName, args.region)

    # Still unable to backup this us-east-1 secret
    if secretName == "jenkins/github":
        continue

    # If a secret name has a '/' in it, use it to create a parent directory in which all such secrets will be stored
    slashCount = secretName.count("/")

    if slashCount == 0:
        # If secret name doesn't have any "/" then it will be saved in region's top level directory
        filename = secretName
        cwd = os.getcwd()
        dir_path = os.path.join(cwd, repoPath, args.region)
    else:
        # Copy all items except last to a new list
        dirPrefixes = secretName.split('/')[:-1]

        # Last items of the list will be the file name
        filename = secretName.split('/')[-1]

        # Create directory path to store the secret
        cwd = os.getcwd()
        # https://stackoverflow.com/a/14826889
        dir_path = os.path.join(cwd, repoPath, args.region, *dirPrefixes)

    # Create the directory path if it doesn't exist already
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    # Create a dictionary having secretDesc and secretValue of the secret
    secretData = {}
    secretData["secretDesc"] = secretDesc
    secretData["secretValue"] = secretValue

    # Create a pretty json of the secret dictionary
    fileContent = json.dumps(secretData, indent=4)

    # Save the json in a file
    file_path = os.path.join(dir_path, filename)
    with open(file_path, 'w') as file:
        file.write(fileContent)

    # Encrypt and remove the plain text file
    kms.encrypt_file(file_path, CMK)
    os.remove(file_path)

# Add/Stage changes to repo
# https://github.com/gitpython-developers/GitPython/issues/292#issuecomment-224548324
repo.git.add(A=True)

# Commit changes to repo
repo.index.commit(args.region + ' AWS secrets backup ' +
                  str(datetime.now().date()))

# Push changes to remote repo
origin = repo.remote('origin')
origin.push()

# Remove the repo copy from system
if os.path.exists(repoPath) and os.path.isdir(repoPath):
    shutil.rmtree(repoPath)
