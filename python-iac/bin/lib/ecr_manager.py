import json
import logging
import base64
import boto3


class EcrManager:
    __client = {}

    @classmethod
    def __get_client(cls, region) -> object:
        if region not in cls.__client:
            cls.__client[region] = boto3.client('ecr', region_name=region)
        return cls.__client[region]

    @classmethod
    def get_registries(cls, region) -> list:
        client = cls.__get_client(region)
        repositoryList = []
        describe_repo_paginator = client.get_paginator('describe_repositories')
        for repo_paginator_page in describe_repo_paginator.paginate():
            for repo in repo_paginator_page['repositories']:
                repositoryList.append(repo)
        return repositoryList

    @classmethod
    def registry_exists(cls, registry, region) -> bool:

        for key in cls.get_registries(region):
            if registry == key["repositoryName"]:
                return True
        return False

    @classmethod
    def create_registry(cls, registry, region) -> None:
        client = cls.__get_client(region)
        response = client.create_repository(
            repositoryName=registry,
            encryptionConfiguration={
                'encryptionType': 'AES256'
            }
        )

        repository_response = response.get('repository', {})
        registry_id = repository_response.get('registryId')
        repository_name = repository_response.get('repositoryName')
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
                        "countNumber": 5
                    },
                    "action": {
                        "type": "expire"
                    }
                }
            ]
        })

        put_lifecycle_response = client.put_lifecycle_policy(
            registryId=registry_id,
            repositoryName=repository_name,
            lifecyclePolicyText=lifecycle_policy_text,
        )

        logging.debug(f"{response=}\n{put_lifecycle_response=}")

    @classmethod
    def get_erc_credentials(cls, region):

        client = cls.__get_client(region)
        ecr_credentials = client.get_authorization_token()
        autorization_data = ecr_credentials['authorizationData'][0]

        ecr_username = 'AWS'
        ecr_password = (
            base64.b64decode(autorization_data['authorizationToken'])
            .replace(b'AWS:', b'')
            .decode('utf-8')
        )

        ecr_url = autorization_data['proxyEndpoint'].strip('https://')

        return ecr_username, ecr_password, ecr_url
