#!/usr/bin/python

import argparse
import lib.secrets_manager as secrets
import lib.params as params
import json
import lib.kms as kms
import os
import shutil

# https://gitpython.readthedocs.io/en/stable/intro.html
# https://gitpython.readthedocs.io/en/stable/tutorial.html
from git import Repo

parser = argparse.ArgumentParser()
parser.add_argument('--srcRegion',  help='Secret manager source region')
parser.add_argument('--destRegion', help='Secrets manager destination region')
parser.add_argument('--srcEnvName', help='Source Secret or the source environment prefix name. Type "all" will copy all secrets')
parser.add_argument('--destEnvName', help='Destination environment prefix name')
parser.add_argument('--deployEKS', help='Pass on the flag whether EKS deployment is true or not')
parser.add_argument('--skipSecrets', help='Secrets to skip during restoration. Example \'aurora-mysql-cluster,aurora-postgresql-cluster\' but if env prefix is \'all\' then specify full secret name here like \'openvpn/server\'')
args = parser.parse_args()

def exist_in_skipsecret(secretName, destEnvName, skipSecrets):
    if "/" in destEnvName:
        dstEnvPrefix = destEnvName.split('/')[0]
    else:
        dstEnvPrefix = destEnvName

    listOfSecrets = []
    prefix = dstEnvPrefix + '/'

    for secret in skipSecrets.strip('\'').split(','):
        listOfSecrets.append(prefix + secret.strip())

    stringOfSecrets = ' '.join(listOfSecrets)

    if secretName in stringOfSecrets:
        return True
    else:
        return False


def secret_exists_already(secretName, destRegion):
    existInRegion = secrets.describe_secret(secretName, destRegion)
    if existInRegion is None:
        return False
    else:
        return True


def change_secret_envname(srcEnvName, destEnvName):
    if "/" in srcEnvName and "/" in destEnvName:
        srcEnvPrefix = srcEnvName.split('/')[0]
        dstEnvPrefix = destEnvName.split('/')[0]

        # change secret envName if needed
        if srcEnvPrefix in "develop qa main" and srcEnvPrefix != dstEnvPrefix and dstEnvPrefix is not None:
            stripEnv = srcEnvName.split(srcEnvPrefix, 1)[1]
            secretName = dstEnvPrefix + stripEnv
        else:
            secretName = srcEnvName
    elif "/" in srcEnvName:
        srcEnvPrefix = srcEnvName.split('/')[0]

        # change secret envName if needed
        if srcEnvPrefix in "develop qa main" and srcEnvPrefix != destEnvName and destEnvName is not None:
            stripEnv = srcEnvName.split(srcEnvPrefix, 1)[1]
            secretName = destEnvName + stripEnv
        else:
            secretName = srcEnvName
    else:
        secretName = srcEnvName

    return secretName


def restore_all_secrets(secretName, destRegion):
    # Decrypt the secret file
    kms.decrypt_file(secretName)

    # Open and read the secret file
    with open(secretName + ".decrypted", 'r') as file:
        secretData = json.load(file)

    # Remove the plain text file
    os.remove(secretName + ".decrypted")

    # parse the data from secret file
    secretDesc = secretData["secretDesc"]
    if type(secretData["secretValue"]) is dict:
        secretValue = json.dumps(secretData["secretValue"])
    else:
        secretValue = secretData["secretValue"]

    # Restore the secret
    secrets.create_secret(secretName, secretValue, secretDesc, destRegion)


def restore_the_secret(srcEnvName, destEnvName, destRegion):
    # Decrypt the secret file
    kms.decrypt_file(srcEnvName)

    # Open and read the secret file
    with open(srcEnvName + ".decrypted", 'r') as file:
        secretData = json.load(file)

    # Remove the plain text file
    os.remove(srcEnvName + ".decrypted")

    # parse the data from secret file
    secretDesc = secretData["secretDesc"]
    if type(secretData["secretValue"]) is dict:
        secretValue = json.dumps(secretData["secretValue"])
    else:
        secretValue = secretData["secretValue"]

    secretName = change_secret_envname(srcEnvName, destEnvName)

    # Restore the secret
    secrets.create_secret(secretName, secretValue, secretDesc, destRegion)

def restoreSecrets(dstEnvPrefix, destRegion, srcRegion, srcEnvName, skipSecrets, deployEKS):
    # temporary fix to stop this script if eks was not deployed
    if deployEKS == "true":

        repoURL = "git@github.com:RepTrak/devops-secretsmanager.git"
        repoPath = "devops-secretsmanager"
        codeDir = os.getcwd()

        # Clone the repo in a local path
        repo = Repo.clone_from(repoURL, repoPath)

        basePath = os.path.join(repoPath, srcRegion)
        os.chdir(basePath)

        # If provided secret name is of a single secret, restore it if it doesn't exist already in the region
        if os.path.isfile(srcEnvName + ".encrypted"):
            secret_exists = secret_exists_already(args.destEnvName, destRegion)
            in_skipsecret = exist_in_skipsecret(args.destEnvName, args.destEnvName, skipSecrets)

            if secret_exists and not in_skipsecret:
                print("Secret " + srcEnvName + " already exists in " + destRegion + ", delete it first if you like to restore the backup from repo")
            elif secret_exists and in_skipsecret:
                print("Secret " + srcEnvName + " already exists in " + destRegion + " and it's in Skip list, so skipping it...")
            else:
                restore_the_secret(srcEnvName, args.destEnvName, destRegion)

        # If "all" is provided as secret name then all secrets of that region will be restored
        elif srcEnvName == "all":
            relativePath = os.path.relpath(".")

            for (dirpath, dirnames, filenames) in os.walk(relativePath):
                for files in filenames:

                    path = os.path.normpath(os.path.join(dirpath, files))

                    if os.path.isfile(path):
                        secretSrcName = os.path.splitext(path)[0]
                        secret_exists = secret_exists_already(secretSrcName, destRegion)
                        in_skipsecret = exist_in_skipsecret(secretSrcName, args.destEnvName, skipSecrets)

                        if secret_exists and not in_skipsecret:
                            print("Secret " + secretSrcName + " already exists in " + destRegion + ", delete it first if you like to restore the backup from repo")
                        elif secret_exists and in_skipsecret:
                            print("Secret " + secretSrcName + " already exists in " + destRegion + " and it's in Skip list, so skipping it...")
                        else:
                            restore_all_secrets(secretSrcName, destRegion)

        else:
            dirOfSecrets = os.path.join(basePath, srcEnvName)
            relativePath = os.path.relpath(dirOfSecrets, basePath)

            # If provided secret name is a env prefix, then all of those secrets from that directory will be restored
            for (dirpath, dirnames, filenames) in os.walk(relativePath):
                for files in filenames:

                    path = os.path.normpath(os.path.join(dirpath, files))

                    if os.path.isfile(path):
                        secretSrcName = os.path.splitext(path)[0]
                        secretName = change_secret_envname(secretSrcName, args.destEnvName)
                        secret_exists = secret_exists_already(secretName, destRegion)
                        in_skipsecret = exist_in_skipsecret(secretName, args.destEnvName, skipSecrets)

                        if secret_exists and not in_skipsecret:
                            print("Secret " + secretName + " already exists in " + destRegion + ", delete it first if you like to restore the backup from repo")
                        elif secret_exists and in_skipsecret:
                            print("Secret " + secretName + " already exists in " + destRegion + " and it's in Skip list, so skipping it...")
                        else:
                            restore_the_secret(secretSrcName, args.destEnvName, destRegion)

        # Remove the repo copy from system
        os.chdir(codeDir)
        if os.path.exists(repoPath) and os.path.isdir(repoPath):
            shutil.rmtree(repoPath)

    else:
        print("")
        print("DeployEKS is false for " + dstEnvPrefix + " env in " + destRegion + " region, so nothing to be done here")

if "/" in args.destEnvName:
    dstEnvPrefix = args.destEnvName.split('/')[0]
else:
    dstEnvPrefix = args.destEnvName

if args.srcRegion is not None:
    srcRegion = args.srcRegion

if args.srcEnvName is not None:
    srcEnvName = args.srcEnvName

if args.skipSecrets is not None:
    skipSecrets = args.skipSecrets

if args.deployEKS is not None:
    deployEKS = args.deployEKS

if args.destRegion is None:
    # Create a list of all regions of the env
    paramsDir = "./params/" + dstEnvPrefix + "/"
    regions = [ name for name in os.listdir(paramsDir) if os.path.isdir(os.path.join(paramsDir, name)) ]
    print("")
    print("For " + dstEnvPrefix + " env, selected regions are " + ", ".join(regions))

    # Loop through the list of regions and perform the selected action on every region
    for region in regions:
        # load params into memory
        params.load_params_mem(dstEnvPrefix, region)
        destRegion = os.environ["Region"]
        srcRegion = os.environ["SecretSrcRegion"]
        srcEnvName = os.environ["SecretSrcEnvName"]
        skipSecrets = os.environ["SkipSecrets"]
        deployEKS = os.environ["DeployEKS"]
        print("")
        print("Restoring secrets of " + dstEnvPrefix + " env in " + destRegion + " region")
        print("")
        restoreSecrets(dstEnvPrefix, destRegion, srcRegion, srcEnvName, skipSecrets, deployEKS)
else:
    destRegion = args.destRegion
    restoreSecrets(dstEnvPrefix, destRegion, srcRegion, srcEnvName, skipSecrets, deployEKS)
