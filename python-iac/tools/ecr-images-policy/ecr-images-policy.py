import boto3
from pprint import pprint
import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument("--action", required=True, choices=["get-lifecycle-policy", "set-lifecycle-policy"], help="Action to be taken against repositorys")
parser.add_argument("--repoName", required=False, default=None, help="Action to be taken against repositorys")
parser.add_argument("--pruneAllImagesCount", required=False, type=int, default=5, help="Count of images that will be kept in repository")
parser.add_argument("--region", required=True, help="region for ECR")
args = parser.parse_args()

# Create a client
ecr_client = boto3.client('ecr', region_name=args.region)

def parse_lifecycle_policy_text(lifecyclePolicyText):
    lifecyclePolicyTextDict = json.loads(lifecyclePolicyText)
    policyList = []

    for rule in range(len(lifecyclePolicyTextDict['rules'])):
        policyType = lifecyclePolicyTextDict['rules'][rule]['selection']['countType']

        if policyType == "imageCountMoreThan":
            actionPrint = ""
            tagStatusPrint = ""
            countNumber = lifecyclePolicyTextDict['rules'][rule]['selection']['countNumber']
            action = lifecyclePolicyTextDict['rules'][rule]['action']['type']
            tagStatus = lifecyclePolicyTextDict['rules'][rule]['selection']['tagStatus']
            if action == "expire":
                actionPrint = "Remove"

            if tagStatus == "any":
                tagStatusPrint = "all"
            else:
                tagStatusPrint = tagStatus

            policyList.append(f"{actionPrint} {tagStatusPrint} images except recent {countNumber}")

        if policyType == "sinceImagePushed":
            actionPrint = ""
            tagStatusPrint = ""
            countNumber = lifecyclePolicyTextDict['rules'][rule]['selection']['countNumber']
            countUnit = lifecyclePolicyTextDict['rules'][rule]['selection']['countUnit']
            action = lifecyclePolicyTextDict['rules'][rule]['action']['type']
            tagStatus = lifecyclePolicyTextDict['rules'][rule]['selection']['tagStatus']
            if action == "expire":
                actionPrint = "Remove"

            if tagStatus == "any":
                tagStatusPrint = "all"
            else:
                tagStatusPrint = tagStatus

            policyList.append(f"{actionPrint} {tagStatusPrint} images older then {countNumber} {countUnit}")

    return ". ".join(policyList)


def get_lifecycle_policy(repoName, repoCount):
    policyFormat = "{:>3d} | {:<40s} | {:^13d} | {:^15d} | {:s}"
    taggedImageCount = 0
    untaggedImageCount = 0
    describe_image_paginator = ecr_client.get_paginator('describe_images')
    for image_paginator_page in describe_image_paginator.paginate(repositoryName=repoName):
        for image in image_paginator_page['imageDetails']:
            if 'imageTags' in image:
                taggedImageCount += 1
            else:
                untaggedImageCount += 1

    try:
        response = ecr_client.get_lifecycle_policy(repositoryName=repoName)
        print(policyFormat.format(repoCount, repoName, taggedImageCount, untaggedImageCount, parse_lifecycle_policy_text(response['lifecyclePolicyText'])))
    except ecr_client.exceptions.LifecyclePolicyNotFoundException:
        print(policyFormat.format(repoCount, repoName, taggedImageCount, untaggedImageCount, "No Lifecycle policy"))
    except Exception:
        print("Exception while getting lifecycle policy")
        raise


def set_lifecycle_policy(repoName, pruneAllImagesCount):
    lifecycle_policy_text = json.dumps({
        "rules": [
            {
                "rulePriority": 19,
                "description": "prune untagged images",
                "selection": {
                    "tagStatus": "untagged",
                    "countType": "imageCountMoreThan",
                    "countNumber": 1
                },
                "action": {
                    "type": "expire"
                }
            },
            {
                "rulePriority": 20,
                "description": "prune images",
                "selection": {
                    "tagStatus": "any",
                    "countType": "imageCountMoreThan",
                    "countNumber": pruneAllImagesCount
                },
                "action": {
                    "type": "expire"
                }
            }
        ]
    })

    try:
        ecr_client.put_lifecycle_policy(
            repositoryName=repoName,
            lifecyclePolicyText=lifecycle_policy_text,
        )

        print(f"Lifecycle policies have been applied to {repoName}")
    except Exception:
        print(f"Exception while setting lifecycle policies on {repoName} repository")
        raise

if args.action == "get-lifecycle-policy":
    policyHeaderFormat = "{:>3s} | {:<40s} | {:>13s} | {:>15s} | {:s}"

    print("{:-<160s}".format(""))
    print(policyHeaderFormat.format("###", "Repository", "Tagged Images", "Untagged Images", "Repository Policies"))
    print("{:-<160s}".format(""))

    if args.repoName is None:
        describe_repo_paginator = ecr_client.get_paginator('describe_repositories')
        repoCount = 1

        for repo_paginator_page in describe_repo_paginator.paginate():
            for repo in repo_paginator_page['repositories']:
                repoName = repo['repositoryName']
                get_lifecycle_policy(repoName, repoCount)
                repoCount += 1
    else:
        repoName = args.repoName
        get_lifecycle_policy(repoName, repoCount=1)


if args.action == "set-lifecycle-policy":

    if args.repoName is None:
        describe_repo_paginator = ecr_client.get_paginator('describe_repositories')

        for repo_paginator_page in describe_repo_paginator.paginate():
            for repo in repo_paginator_page['repositories']:
                repoName = repo['repositoryName']
                set_lifecycle_policy(repoName, args.pruneAllImagesCount)
    else:
        repoName = args.repoName
        set_lifecycle_policy(repoName, args.pruneAllImagesCount)

