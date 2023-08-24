import boto3
from pprint import pprint
import time
import logging

# https://stackoverflow.com/a/61663920
def get_zone_id(zone_name):
    client = boto3.client('route53')

    response = client.list_hosted_zones_by_name(
        DNSName=zone_name,
        MaxItems='1'
    )
    if ('HostedZones' in response.keys() and len(response['HostedZones']) > 0 and response['HostedZones'][0]['Name'].startswith(zone_name)):
        hostedZoneId = response['HostedZones'][0]['Id'].split('/')[2]
        return hostedZoneId
    else:
        exit(f"HostedZone not found: {zone_name}")


def get_alb_hostedzoneid(region, alb_address):
    elbv2 = boto3.client('elbv2', region)
    try:
        alb_name = "-".join(alb_address.replace('internal-','').split(".")[0].split("-")[:-1])
        response = elbv2.describe_load_balancers(
            Names=[ alb_name ],
        )
        albHostedZoneId = response['LoadBalancers'][0]['CanonicalHostedZoneId']
    except Exception as e:
        exit(f"Failed to fetch {alb_address} ALB's hostedzoneid\n{e}")

    return albHostedZoneId


def get_hostedzoneid_by_listrecords(region, zone_id, dns_record, points_to):
    client = boto3.client('route53')
    recordName = f"{dns_record}."
    recordTarget = f"{points_to}."
    dnsHostedZoneId = None

    try:
        response = client.list_resource_record_sets(
            HostedZoneId=zone_id,
            StartRecordName=dns_record,
            StartRecordType='A',
            StartRecordIdentifier=region,
        )
        for record in range(len(response['ResourceRecordSets'])):
            if response['ResourceRecordSets'][record]['Type'] == "A" and response['ResourceRecordSets'][record]['Name'] == recordName and response['ResourceRecordSets'][record]['AliasTarget']['DNSName'] == recordTarget and response['ResourceRecordSets'][record]['Region'] == region:
                dnsHostedZoneId = response['ResourceRecordSets'][record]['AliasTarget']['HostedZoneId']
                response['ResourceRecordSets'][record]
        return dnsHostedZoneId
    except Exception as e:
        exit(f"Failed to fetch {recordTarget} ALB's hostedzoneid\n{e}")


def dns_record_change_status(dns_record_id):
    client = boto3.client('route53')
    response = client.get_change(Id=dns_record_id)
    while response["ChangeInfo"]["Status"] == "PENDING":
        time.sleep(1)
        response = client.get_change(Id=dns_record_id)


def dns_record_action(region, zone_id, dnsAction, dns_record, points_to, HostedZoneId, addressType):
    client = boto3.client('route53')

    if addressType == "ALB":
        dns_entry = {
            'Changes': [
                {
                    'Action': dnsAction,
                    'ResourceRecordSet': {
                        'Name': dns_record,
                        'Type': 'A',
                        'SetIdentifier': region,
                        'Region': region,
                        'AliasTarget': {
                            'HostedZoneId': HostedZoneId,
                            'DNSName': points_to,
                            'EvaluateTargetHealth': True
                        },
                    },
                },
            ],
        }

    elif addressType == "Cloudfront":
        dns_entry = {
            'Changes': [
                {
                    'Action': dnsAction,
                    'ResourceRecordSet': {
                        'Name': dns_record,
                        'Type': 'A',
                        'AliasTarget': {
                            'HostedZoneId': HostedZoneId,
                            'DNSName': points_to,
                            'EvaluateTargetHealth': False
                        },
                    },
                },
            ],
        }


    if dnsAction == "UPSERT":
        # Just for the print statement
        dnsAction = "create/update"
    if dnsAction == "DELETE":
        # Just for the print statement
        dnsAction = "delete"

    try:
        response = client.change_resource_record_sets(HostedZoneId=zone_id, ChangeBatch=dns_entry)
        dns_record_id = response["ChangeInfo"]["Id"]
        dns_record_change_status(dns_record_id)
    except Exception as e:
        exit(f"{dnsAction.title()} action of {dns_record} has failed\n{e}")

    logging.info(f"{dnsAction.title()} action of {dns_record} completed successfully")


def create_or_update_dns_record(region, zone_name, dns_record, points_to, addressType):
    dnsAction = "UPSERT"
    zone_id = get_zone_id(zone_name)
    if addressType == "ALB":
        albHostedZoneId = get_alb_hostedzoneid(region, points_to)
        dns_record_action(region, zone_id, dnsAction, dns_record, points_to, albHostedZoneId, addressType)
    elif addressType == "Cloudfront":
        HostedZoneId = "Z2FDTNDATAQYW2"
        dns_record_action(region, zone_id, dnsAction, dns_record, points_to, HostedZoneId, addressType)

def delete_dns_record(region, zone_name, dns_record, points_to, addressType):
    dnsAction = "DELETE"
    zone_id = get_zone_id(zone_name)
    if addressType == "ALB":
        albHostedZoneId = get_hostedzoneid_by_listrecords(region, zone_id, dns_record, points_to)
        if albHostedZoneId is not None:
            dns_record_action(region, zone_id, dnsAction, dns_record, points_to, albHostedZoneId, addressType)
    elif addressType == "Cloudfront":
        HostedZoneId= "Z2FDTNDATAQYW2"
        dns_record_action(region, zone_id, dnsAction, dns_record, points_to, HostedZoneId, addressType)

def delete_old_resource_record_sets(route53_client, zone_id, dns_record, ResourceRecordSets):
            Changes = []
            dnsAction = "DELETE"

            for record in ResourceRecordSets:
                Changes.append(
                    {
                        'Action': dnsAction,
                        'ResourceRecordSet': record,
                    },
                )
            dns_entry = {
                'Changes': Changes,
            }

            pprint(dns_entry)

            try:
                response = route53_client.change_resource_record_sets(HostedZoneId=zone_id, ChangeBatch=dns_entry)
                dns_record_id = response["ChangeInfo"]["Id"]
                dns_record_change_status(dns_record_id)
                logging.info(f"{dnsAction.title()} action of {dns_record} completed successfully")
            except Exception as e:
                exit(f"{dnsAction.title()} action of {dns_record} has failed\n{e}")

def delete_old_dns_record(region, zone_name, dns_record, addressType):
    zone_id = get_zone_id(zone_name)

    route53_client = boto3.client('route53')
    recordName = f"{dns_record}."

    if addressType == "ALB":
        ResourceRecordSets = []
        try:
            response = route53_client.list_resource_record_sets(
                HostedZoneId=zone_id,
                StartRecordName=dns_record,
                StartRecordType='A',
                StartRecordIdentifier=region,
            )
            for record in range(len(response['ResourceRecordSets'])):
                if response['ResourceRecordSets'][record]['Name'] == recordName and response['ResourceRecordSets'][record]['Type'] == "A" and "Region" in response['ResourceRecordSets'][record].keys():
                    ResourceRecordSets.append(response['ResourceRecordSets'][record])
        except Exception as e:
            exit(f"Failed to fetch {recordName} dns record that needs to be deleted\n{e}")

        if len(ResourceRecordSets) > 0:
            logging.info(f"Removing old Latency based routing policy dns records of {dns_record}")
            delete_old_resource_record_sets(route53_client, zone_id, dns_record, ResourceRecordSets)

    elif addressType == "Cloudfront":
        ResourceRecordSets = []
        try:
            response = route53_client.list_resource_record_sets(
                HostedZoneId=zone_id,
                StartRecordName=dns_record,
                StartRecordType='A',
            )
            for record in range(len(response['ResourceRecordSets'])):
                if response['ResourceRecordSets'][record]['Name'] == recordName and response['ResourceRecordSets'][record]['Type'] == "A" and "Region" not in response['ResourceRecordSets'][record].keys():
                    ResourceRecordSets.append(response['ResourceRecordSets'][record])
        except Exception as e:
            exit(f"Failed to fetch {recordName} dns record that needs to be deleted\n{e}")

        if len(ResourceRecordSets) > 0:
            logging.info(f"Removing old Simple routing policy dns records of {dns_record}")
            delete_old_resource_record_sets(route53_client, zone_id, dns_record, ResourceRecordSets)

    elif addressType == "old-CNAME":
        ResourceRecordSets = []
        try:
            response = route53_client.list_resource_record_sets(
                HostedZoneId=zone_id,
                StartRecordName=dns_record,
                StartRecordType='CNAME',
            )
            for record in range(len(response['ResourceRecordSets'])):
                if response['ResourceRecordSets'][record]['Name'] == recordName and response['ResourceRecordSets'][record]['Type'] == "CNAME" and "Region" not in response['ResourceRecordSets'][record].keys():
                    ResourceRecordSets.append(response['ResourceRecordSets'][record])
        except Exception as e:
            exit(f"Failed to fetch {recordName} dns record that needs to be deleted\n{e}")

        if len(ResourceRecordSets) > 0:
            logging.info(f"Removing old CNAME dns records of {dns_record}")
            delete_old_resource_record_sets(route53_client, zone_id, dns_record, ResourceRecordSets)
