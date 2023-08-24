import boto3
from botocore.exceptions import ClientError

from .core_components import AwsServiceManager


def tag_subnet(resourceName, key, value, region):
    client = boto3.resource("ec2", region_name=region)
    subnet = client.Subnet(resourceName)
    try:
        response = subnet.create_tags(Tags=[{"Key": key, "Value": value}])
    except ClientError as e:
        response = e

    return response


class EC2Manager(AwsServiceManager):
    service = "ec2"

    @classmethod
    def get_transit_gateway_id(cls, region) -> str:
        client = cls.get_client(region)
        try:
            response = client.describe_transit_gateways()
            return response["TransitGateways"][0]["TransitGatewayId"]
        except Exception:
            return ""
