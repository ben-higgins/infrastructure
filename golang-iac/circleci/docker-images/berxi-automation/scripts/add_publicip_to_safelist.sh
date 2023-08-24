#!/bin/bash

echo "add_publicip_to_safelist starting"

# script arguments
env=${1:-dev}
if [[ $env = "prod" ]]; then
    echo "Unable to safelist an ip address in production using this script";
    exit 1;
fi

# Retrieves the build machines external ip address
public_ip_address=$(wget -qO- http://checkip.amazonaws.com)
if [[ $public_ip_address = "" ]]; then
    echo "Unable to identify a valid public ip address";
    exit 1;
fi

# Extract the Security Group where we want to register the ip address
sg_name="${env}_sg_test_automation"
sg_id=$(aws ec2 describe-security-groups \
    --query 'SecurityGroups[].[GroupName, GroupId]' \
    --filters Name=group-name,Values=$sg_name \
    --output table --profile $env \
    | grep $sg_name | awk '{print $4}')

# this isn't quite working yet.  basically want to confirm the sg_id variable has a valid value
# null and emtpy string are bad
#if [ -z "${sg_id}" ]; then
#    echo "Unable to find valid security group ${sg_name}"
#fi

# Update the security group with the public ip address

# TODO: Future may want to account for the IP address already existing, but 
# phase 1 this assumes we are executing tests within a ci build process
# and the IP is removed once the test is complete

# if you try to submit a duplicate ipaddress you will get a duplicate error from aws
# error message looks like the following:
# 
# An error occurred (InvalidPermission.Duplicate) when calling the AuthorizeSecurityGroupIngress operation: 
# the specified rule "peer: 108.26.160.203/32, TCP, from port: 443, to port: 443, ALLOW" already exists
ip_permissions='[{"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": [{"CidrIp": "'${public_ip_address}/32'", "Description": "CircleCI"}]}]';
aws ec2 authorize-security-group-ingress --profile $env --group-id $sg_id --ip-permissions "${ip_permissions}"
if [ "$?" != "0" ];
then
    echo "There was an issue adding the ip address to the safelist";
    exit 1;
fi

echo "$public_ip_address added to security group $sg_name, id: $sg_id";
echo "add_public_to_safelist complete";
