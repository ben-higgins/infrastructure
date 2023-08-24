#!/bin/bash
## ./tools/aws-mgnt/get-vpc-dependencies.sh vpc-05f99d0b8bcb5564b eu-west-1
vpc=$1
aws ec2 describe-internet-gateways --filters 'Name=attachment.vpc-id,Values='$vpc --region $2 | grep InternetGatewayId
aws ec2 describe-subnets --filters 'Name=vpc-id,Values='$vpc --region $2 | grep SubnetId
aws ec2 describe-route-tables --filters 'Name=vpc-id,Values='$vpc --region $2 | grep RouteTableId
aws ec2 describe-network-acls --filters 'Name=vpc-id,Values='$vpc --region $2 | grep NetworkAclId
aws ec2 describe-vpc-peering-connections --filters 'Name=requester-vpc-info.vpc-id,Values='$vpc --region $2 | grep VpcPeeringConnectionId
aws ec2 describe-vpc-endpoints --filters 'Name=vpc-id,Values='$vpc --region $2 | grep VpcEndpointId
aws ec2 describe-nat-gateways --filter 'Name=vpc-id,Values='$vpc --region $2 | grep NatGatewayId
aws ec2 describe-security-groups --filters 'Name=vpc-id,Values='$vpc --region $2 | grep GroupId
aws ec2 describe-instances --filters 'Name=vpc-id,Values='$vpc --region $2 | grep InstanceId
aws ec2 describe-vpn-connections --filters 'Name=vpc-id,Values='$vpc --region $2 | grep VpnConnectionId
aws ec2 describe-vpn-gateways --filters 'Name=attachment.vpc-id,Values='$vpc --region $2 | grep VpnGatewayId
aws ec2 describe-network-interfaces --filters 'Name=vpc-id,Values='$vpc --region $2 | grep NetworkInterfaceId
