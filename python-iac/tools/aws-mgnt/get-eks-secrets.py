#!/usr/bin/python

import boto3
import argparse
from typing import Tuple
from textwrap import dedent


ap = argparse.ArgumentParser()
ap.add_argument("--region", required=False,
                help="AWS region EKS was deployed to")
ap.add_argument("--envName", required=False,
                help="Branch equals environment to deploy to")

args = vars(ap.parse_args())

client = boto3.client('cloudformation', region_name=args["region"])


def retrieve_kube_config(stackName: str, client: object) -> Tuple[str]:

    acces_key = ""
    access_secret = ""
    eks_config_command = ""

    response = client.describe_stacks(StackName=stackName)

    outputs = response["Stacks"][0]["Outputs"]

    for output in outputs:

        if output["OutputKey"] == "AccessKey":
            acces_key = output["OutputValue"]
            continue

        if output["OutputKey"] == "AccessSecret":
            access_secret = output["OutputValue"]
            continue

        if output["OutputKey"] == "EKSConfig":
            eks_config_command = output["OutputValue"]
            continue

    return acces_key, access_secret, eks_config_command


def print_kube_config_steps(
    acces_key: str, access_secret: str, eks_config_command: str, env: str
) -> None:

    get_kube_token_command = (
        "kubectl -n kube-system describe secret "
        "$(kubectl -n kube-system get secret | grep eks-admin "
        "| awk '{print $1}')"
    )
    kubernetes_dashboard_url = (
        "http://localhost:8001/api/v1/"
        "namespaces/kubernetes-dashboard/services/"
        "https:kubernetes-dashboard:/proxy/#!/login"
    )

    print(
        dedent(
            f"""
            --------------------------------------------------------
            ---------- EKS CLUSTER CONFIG INSTRUCTIONS -------------
            --------------------------------------------------------
            Paste the following in your ~/.aws/credentials file:
            [{env}]
            aws_access_key_id={acces_key}
            aws_secret_access_key={access_secret}

            Next, to set your CLI to use the above credentials, run:
            $>export AWS_PROFILE={env}
            Finally, to configure our local CLI to use the EKS
            `~/kubeconfig` for EKS, run:
            $>{eks_config_command}

            To generate the token to access the kubenetes dashboard, run:
            $>{get_kube_token_command}

            Grab the token and run:
            $>kubectl proxy

            You can access the dashboard at:
            {kubernetes_dashboard_url}
            
            Choose Token and paste the authentication_token from the previous command"""
        )
    )


response = client.list_stacks(
    StackStatusFilter=[
        'CREATE_COMPLETE',
        'ROLLBACK_IN_PROGRESS',
        'ROLLBACK_FAILED',
        'ROLLBACK_COMPLETE',
        'UPDATE_IN_PROGRESS',
        'UPDATE_COMPLETE',
        'UPDATE_ROLLBACK_FAILED',
        'UPDATE_ROLLBACK_COMPLETE',
    ]
)

stackList = response.get("StackSummaries", [])

for item in stackList:

    stackString = f"{args['envName']}-Eks"

    if stackString in item["StackName"]:

        acces_key, access_secret, eks_config_command = retrieve_kube_config(
            stackName=item["StackName"], client=client
        )

        print_kube_config_steps(
            acces_key,
            access_secret,
            eks_config_command,
            args['envName']
        )

        break
else:
    print(f"No stack found for {args['envName']}")
