import boto3
from botocore.exceptions import ClientError

def tag_subnet(resourceName, key, value, region):
    client = boto3.resource('ec2', region_name=region)
    subnet = client.Subnet(resourceName)
    try:
        response = subnet.create_tags(
            Tags=[
                {
                    'Key': key,
                    'Value': value
                }
            ]
        )
    except ClientError as e:
        response = e

    return response
