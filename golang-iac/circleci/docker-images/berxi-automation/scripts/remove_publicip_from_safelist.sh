#!/bin/bash

echo "remove_publicip_from_safelist starting"

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

ip_permissions='[{"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": [{"CidrIp": "'${public_ip_address}/32'", "Description": "CircleCI"}]}]';
aws ec2 revoke-security-group-ingress --profile $env --group-id $sg_id --ip-permissions "${ip_permissions}"
if [ "$?" != "0" ];
then
    echo "There was an issue removing the ip address from the safelist";    
    exit 1;
fi

echo "$public_ip_address removed from security group $sg_name, id: $sg_id";
echo "remove_publicip_from_safelist complete";
