import boto3

def get_nested_name(envName, nestName, region):
    parentName = stack_exist(envName, region)
    response = stack_details(parentName, region)
    for output in response["Stacks"][0]["Outputs"]:
        if output["OutputKey"] == nestName:
            response = stack_details(output["OutputValue"], region)
            return response["Stacks"][0]["StackName"]


def get_stack_output(stackName, key, region):
    response = stack_details(stackName, region)
    outputs =  response["Stacks"][0]["Outputs"]
    for output in outputs:
        if output["OutputKey"] == key:
            return output["OutputValue"]


# returns None or the Stack Name
def stack_exist(envName, region):
    # get list of stacks in region
    client = boto3.client('cloudformation', region_name=region)
    response = client.list_stacks(
        StackStatusFilter=[
            'CREATE_COMPLETE','ROLLBACK_IN_PROGRESS','ROLLBACK_FAILED','ROLLBACK_COMPLETE','UPDATE_IN_PROGRESS','UPDATE_COMPLETE','UPDATE_ROLLBACK_FAILED','UPDATE_ROLLBACK_COMPLETE'
        ]
    )

    # check if stack exists in list
    stackName = None
    stackList = response["StackSummaries"]
    for item in stackList:
        if envName == item["StackName"]:
            stackName = item["StackName"]

    return stackName


def stack_status(stackName, region):
    client = boto3.client('cloudformation', region_name=region)
    response = client.describe_stacks(StackName=stackName)
    results = response["Stacks"][0]["StackStatus"]
    return results


def stack_details(stackName, region):
    client = boto3.client('cloudformation', region_name=region)
    response = client.describe_stacks(StackName=stackName)
    return response


def get_cluster(branchName, region):
    client = boto3.client('cloudformation', region_name=region)
    #get stack name from cloudformation
    response = client.list_stacks(StackStatusFilter=[
        'CREATE_COMPLETE',
        'ROLLBACK_FAILED',
        'ROLLBACK_COMPLETE',
        'UPDATE_COMPLETE',
        'UPDATE_ROLLBACK_COMPLETE',
    ])
    for key in response['StackSummaries']:
        if branchName + "-Eks" in key['StackName']:
            clusterName = key['StackName']
            print("EKS cluster name: " + clusterName)
            return clusterName
