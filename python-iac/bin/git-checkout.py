#!/usr/bin/python

import argparse
from git import Repo
import os

parser = argparse.ArgumentParser()
parser.add_argument("--envName", required = True, help = "Required: Environment name equals environment to deploy to")
parser.add_argument("--gitBranch", required = True, help = "Required: Git branch for deployment")
args = parser.parse_args()

def get_githash():
    repo = Repo(search_parent_directories=True)
    sha = repo.head.commit.hexsha
    short_sha = repo.git.rev_parse(sha)
    return short_sha

def parse_envName(envName):
    # value might come in with a prefix
    try:
        branch = envName.split('/')[1]
    except:
        branch = envName

    #TODO temporary workaround to assign an environment type of develop if deploying a feature branch
    if branch not in "develop qa main":
        envType = "testing"
    else:
        envType = branch

    return envType


def read_gittag_param(parsedEnvName):
    paramFile = "./params/" + parsedEnvName + "/gittag.params"

    with open(paramFile, "r") as file:
        for line in file:
            if line.strip() and not line.startswith('#'):
                linesplit = line.split(':', 1)
                gittag = linesplit[1].strip()
    return gittag

# Don't checkout to a tag when we are working on any feature branch
if args.gitBranch == 'master':

    # Reading the git tag from the params
    parsedEnvName = parse_envName(args.envName)
    gitTag = read_gittag_param(parsedEnvName)

    print(get_githash())

    # initilazing the repo object with current directory's path
    repo = Repo(os.getcwd())

    # https://gitpython.readthedocs.io/en/stable/tutorial.html#using-git-directly
    # checkout to the specified tag
    gitRepo = repo.git
    gitRepo.checkout(gitTag)
else:
    print(args.gitBranch)



