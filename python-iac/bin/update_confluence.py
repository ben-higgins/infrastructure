import argparse
import os
import re
from datetime import datetime
from pathlib import Path

import boto3
from atlassian import Confluence
from dotenv import load_dotenv

from lib.infrastructure_build_manager import InfrastructureBuildManager


def stack_details(stackName, region):
    client = boto3.client('cloudformation', region_name=region)
    response = client.describe_stacks(StackName=stackName)
    return response


env_path = Path(".") / ".env"

load_dotenv(dotenv_path=env_path)

STACK_PARENT_PAGE = 1657536649

confluence = Confluence(
        url="https://ricloud.atlassian.net/",
        username=os.getenv("CONFLUENCE_USER"),
        password=os.getenv("CONFLUENCE_TOKEN"),
        )

ap = argparse.ArgumentParser()
ap.add_argument("--envName", required=True,
                help="Required: Environment name equals environment to deploy to")

args = vars(ap.parse_args())


def prepare_stack_details(_stack_name, _stack_region):
    _stack_main_details = stack_details(_stack_name, _stack_region)['Stacks'][0]
    _params = ("\n").join([f'|{param["ParameterKey"]}|{param["ParameterValue"]}|' for param in _stack_main_details['Parameters']])
    _outputs = ("\n").join([f'|{param["OutputKey"]}|{param["OutputValue"]}|' if not re.match(r'.*([Ss]ecret|[Pp]ass(?(1)wd|word)|[Pp]ass).*', param[
        "OutputKey"]) else f'|{param["OutputKey"]}|*******|' for param in _stack_main_details['Outputs']])
    return _stack_main_details, _params, _outputs


version_comment = f"Autogerated at: {datetime.today().isoformat()}"

_stack_name = args["envName"]

paramsDir = "./params/" + args["envName"] + "/"

regions_sorted_list = InfrastructureBuildManager.prepare_region_builds(paramsDir, args["envName"])

# Loop through the list of regions and perform the selected action on every region
for region in regions_sorted_list:
    _stack_region = region["RegionName"]
    # load params into memory
    environment = InfrastructureBuildManager.get_build_environment(_stack_region, _stack_name, None)

    _stack_main_details, _params, _outputs = prepare_stack_details(_stack_name, _stack_region)

    _sub_stacks = {}
    for key, output in enumerate(_stack_main_details['Outputs']):
        print(key, output)
        _output_arn = output['OutputValue']
        if re.match(r'^arn.*', _output_arn):
            _output_arn_parts = _output_arn.split('/')
            _sub_stacks[output["OutputKey"]] = prepare_stack_details(_output_arn_parts[1], _stack_region)

    # print(_sub_stacks)

    body = f"""
    h1. {_stack_region} -  {_stack_name}
    - *StackId:* {_stack_main_details['StackId']}
    - *StackName:* {_stack_main_details['StackName']}
    - *Description:* {_stack_main_details['Description']}
    - *StackStatus:* {_stack_main_details['StackStatus']}
    
    h3. Parameters:
    ||ParameterKey||ParameterValue||
    {_params}
    h3. Outputs:
    ||OutputKey||OutputValue||
    {_outputs}    
    """

    for key, data in _sub_stacks.items():
        _stack_main_details, _params, _outputs = data
        body += f"""
    h2.  {_stack_region} -  {key}
    - *StackId:* {_stack_main_details['StackId']}
    - *StackName:* {_stack_main_details['StackName']}
    - *StackStatus:* {_stack_main_details['StackStatus']}
    - *CreationTime:* {_stack_main_details['CreationTime']}
    
    h3. Parameters:
    ||ParameterKey||ParameterValue||
    {_params}
    h3. Outputs:
    ||OutputKey||OutputValue||
    {_outputs}
        """

confluence.update_or_create(
        STACK_PARENT_PAGE,
        _stack_name,
        body,
        representation='wiki',
        version_comment=version_comment,
        )
