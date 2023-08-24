import lib.route53 as route53
import lib.secrets_manager as secrets
import argparse
from subprocess import Popen, PIPE
import time
from lib.kubernetes_manager import KubernetesManager
import boto3
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import logging

parser = argparse.ArgumentParser()
parser.add_argument("--envName", required=True, help="environment name")
parser.add_argument("--region", required=True, help="eks deployed region")
parser.add_argument("--deployCloudfront", required=True, help="deploy cloudfront condition")
parser.add_argument("--regionActingAs", required=True, help="whether the region is master or slave")
args = parser.parse_args()

region = args.region
environment = args.envName
deployCloudfront = args.deployCloudfront
regionActingAs = args.regionActingAs

def read_helm_dnsentry(serviceName):
    p1 = Popen(["helm", "get", "values", serviceName], stdout=PIPE)
    p2 = Popen(["grep", "dnsEntry"], stdin=p1.stdout, stdout=PIPE)
    p3 = Popen(["cut", "-d:", "-f2"], stdin=p2.stdout, stdout=PIPE)
    p4 = Popen(["xargs"], stdin=p3.stdout, stdout=PIPE)
    p5 = Popen(["tr", "-d", "\n"], stdin=p4.stdout, stdout=PIPE)

    dnsEntry = p5.stdout.read().decode("utf-8")

    if dnsEntry != "":
        return dnsEntry
    else:
        return None

def read_helm_enablecloudfront(serviceName):
    p1 = Popen(["helm", "get", "values", serviceName], stdout=PIPE)
    p2 = Popen(["grep", "EnableCloudfront"], stdin=p1.stdout, stdout=PIPE)
    p3 = Popen(["cut", "-d:", "-f2"], stdin=p2.stdout, stdout=PIPE)
    p4 = Popen(["xargs"], stdin=p3.stdout, stdout=PIPE)
    p5 = Popen(["tr", "-d", "\n"], stdin=p4.stdout, stdout=PIPE)

    EnableCloudfront = p5.stdout.read().decode("utf-8")

    if EnableCloudfront != "":
        return EnableCloudfront.lower()
    else:
        return "false"


def construct_dns_entry(serviceName, envName, region):

    # Decide about the dns entry domain, prefix part and dns entry type
    if envName == "main" and (region == "eu-central-1" or region == "us-east-1" or region == "ap-southeast-2"):
        dnsEnvPrefix = ""
        dnsEntryZone = "reptrak.com"

    elif envName == "qa" and region == "eu-west-1":
        dnsEnvPrefix = envName + "-"
        dnsEntryZone = "reptrak.io"

    elif envName == "develop" and region == "eu-west-1":
        dnsEnvPrefix = envName + "-"
        dnsEntryZone = "reptrak.io"

    elif envName == "testing" and (region == "eu-west-1" or region == "us-east-1"):
        dnsEnvPrefix = envName + "-"
        dnsEntryZone = "reptrak.io"

    else:
        dnsEntryZone = None
        dnsEnvPrefix = None

    # Decide about dns entry for service
    if serviceName == 'gateway-proxy':
        dnsEntry = "apigateway"
    else:
        # Read the DNS entry from microservice's helm values
        dnsEntry = read_helm_dnsentry(serviceName)

        # fall back dnsEntry if unable to get dnsEntry from Helm chart
        if dnsEntry is None:
            if serviceName == "react-communications":
                dnsEntry = "platform"
            elif serviceName == "demo-react-communications":
                dnsEntry = "platform-demo"
            elif serviceName == "react-terms-of-use":
                dnsEntry = "register"
            elif serviceName == "codebook":
                dnsEntry = "codebook"
            elif serviceName == "micro-reptrak-audit":
                dnsEntry = "audit"
            elif serviceName == "micro-reptrak-users":
                dnsEntry = "users"
            elif serviceName == "platform-filters":
                dnsEntry = "filters"
            elif serviceName == "powerbi-server":
                dnsEntry = "powerbi"
            elif serviceName == "snak":
                dnsEntry = "snak"
            elif serviceName == "media-client-queries-generator":
                dnsEntry = "query-generator"
            elif serviceName == "survey-ui":
                dnsEntry = "survey"
            elif serviceName == "data-qa-automation":
                dnsEntry = "data-qa-automation"
            else:
                dnsEntry = None

    if dnsEntry is not None and dnsEntryZone is not None:
            dnsEntryName = f"{dnsEnvPrefix}{dnsEntry}.{dnsEntryZone}"
    else:
        logging.warning(f"Failed to construct the DNS entry for {serviceName}")
        dnsEntryName = None
        dnsEntryZone = None

    return dnsEntryName, dnsEntryZone

def get_cf_distribution_domain(cf_alternate_domain):
    cloudfront_client = boto3.client('cloudfront')
    distributions = cloudfront_client.list_distributions()
    if distributions['DistributionList']['Quantity'] > 0:
        for distribution in distributions['DistributionList']['Items']:
            if distribution['Enabled'] == True:
                if distribution['Aliases']['Quantity'] > 0:
                    for alias in distribution['Aliases']['Items']:
                        if alias == cf_alternate_domain:
                            return distribution['DomainName']
    else:
        return None

# Authentication to K8s cluster
try:
    # If running the python script from the pod
    config.load_incluster_config()
except config.ConfigException:
    try:
        #If not in pod, try loading the kubeconfig
        config.load_kube_config()
    except config.ConfigException:
        raise ApiException("Could not configure kubernetes python client")

k8s_client = client.NetworkingV1Api()

# dictionary to store microservice/ingress-address key value pairs
loadbalancersOfServices = {}

while True:
    # list to store microservice names that will be used to remove stale/deleted dns records
    microServicesList = []

    #================================================#
    # For Api Gateway's DNS Entry
    #================================================#
    # Fetch Api Gateway's Addresss
    apiGatewayName = 'gateway-proxy'

    # retrieve gateway-proxy aws ALB address
    try:
        apiGatewayAddress = KubernetesManager.get_service_url("gateway-proxy")

        # Push name of apiGateway's name to list
        microServicesList.append(apiGatewayName)
    except Exception:
        apiGatewayAddress = ""

    # If the apiGateway/alb-address key value pair is new, add it to dict and create DNS record
    if apiGatewayAddress != "" and apiGatewayName not in loadbalancersOfServices:
        print("")
        logging.info(f"{apiGatewayName} is a new entry, so adding it's DNS record")
        dnsEntryName, dnsEntryZone = construct_dns_entry(apiGatewayName, environment, region)

        loadbalancersOfServices[apiGatewayName] = {
            'dnsEntryName': dnsEntryName,
            'dnsEntryZone': dnsEntryZone,
            'albAddress': apiGatewayAddress,
            'enablecdn': 'false'
        }

        if dnsEntryName is not None:
            route53.delete_old_dns_record(region, dnsEntryZone, dnsEntryName, addressType="old-CNAME")

            logging.info(f"Creating dns record {dnsEntryName} pointing to {apiGatewayAddress}")
            route53.create_or_update_dns_record(region, dnsEntryZone, dnsEntryName, apiGatewayAddress, addressType="ALB")
        else:
            loadbalancersOfServices.pop(apiGatewayName)

    # If the apiGateway/alb-address key value pair has an update, add it to dict and update the DNS record
    elif apiGatewayAddress != "" and loadbalancersOfServices[apiGatewayName]['albAddress'] != apiGatewayAddress:
        print("")
        logging.info(f"{apiGatewayName} loadbalancer address has changed, so updating it's DNS record")
        dnsEntryName, dnsEntryZone = construct_dns_entry(apiGatewayName, environment, region)

        loadbalancersOfServices[apiGatewayName] = {
            'dnsEntryName': dnsEntryName,
            'dnsEntryZone': dnsEntryZone,
            'albAddress': apiGatewayAddress,
            'enablecdn': 'false'
        }

        if dnsEntryName is not None:
            logging.info(f"Updating dns record {dnsEntryName} pointing to {apiGatewayAddress}")
            route53.create_or_update_dns_record(region, dnsEntryZone, dnsEntryName, apiGatewayAddress, addressType="ALB")

    #================================================#
    # For Microservices's DNS Entry
    #================================================#
    # Fetch ingress record from EKS API server
    try:
        ingresses = k8s_client.list_ingress_for_all_namespaces(watch=False)
    except ApiException as e:
        logging.warning("Exception when calling NetworkingV1Api->list_ingress_for_all_namespaces: %s\n" % e)

    # Loop through all the items (ingress) received from the K8s API
    for ingress in ingresses.items:
        ingressName = ingress.metadata.name.replace('-ingress', '')

        # Push each name of microservice's Ingress to list
        microServicesList.append(ingressName)

        # Ingress ALB doesn't get the address immediately
        if ingress.status.load_balancer.ingress is not None:
            ingressAddress = ingress.status.load_balancer.ingress[0].hostname
        else:
            ingressAddress = ""

        EnableCloudfront = read_helm_enablecloudfront(ingressName)

        # If the microservice/ingress-address key value pair is new, add it to dict and create DNS record
        if ingressAddress != "" and ingressName not in loadbalancersOfServices:
            print("")
            logging.info(f"{ingressName} is a new entry, so adding it's DNS record")
            dnsEntryName, dnsEntryZone = construct_dns_entry(ingressName, environment, region)

            loadbalancersOfServices[ingressName] = {
                'dnsEntryName': dnsEntryName,
                'dnsEntryZone': dnsEntryZone,
                'albAddress': ingressAddress,
                'enablecdn': EnableCloudfront
            }

            # EnableCloudfront = read_helm_enablecloudfront(ingressName)
            if dnsEntryName is not None:
                if deployCloudfront == "false" or EnableCloudfront == "false":
                    route53.delete_old_dns_record(region, dnsEntryZone, dnsEntryName, addressType="old-CNAME")
                    route53.delete_old_dns_record(region, dnsEntryZone, dnsEntryName, addressType="Cloudfront")
                    dnsEntryNameOrigin = f"origin-{dnsEntryName}"
                    route53.delete_old_dns_record(region, dnsEntryZone, dnsEntryNameOrigin, addressType="ALB")

                    logging.info(f"Creating dns record {dnsEntryName} pointing to {ingressAddress}")
                    route53.create_or_update_dns_record(region, dnsEntryZone, dnsEntryName, ingressAddress, addressType="ALB")

                elif deployCloudfront == "true" and EnableCloudfront == "true":
                    route53.delete_old_dns_record(region, dnsEntryZone, dnsEntryName, addressType="ALB")
                    route53.delete_old_dns_record(region, dnsEntryZone, dnsEntryName, addressType="old-CNAME")

                    dnsEntryNameOrigin = f"origin-{dnsEntryName}"
                    logging.info(f"Creating Cloudfront Origin dns record {dnsEntryNameOrigin} pointing to {ingressAddress}")
                    route53.create_or_update_dns_record(region, dnsEntryZone, dnsEntryNameOrigin, ingressAddress, addressType="ALB")

                    if regionActingAs == "master":

                        # Wait maximum of 10min to get the Cloudfront address
                        timeout_start = time.time()
                        CloudfrontDomainName = get_cf_distribution_domain(dnsEntryName)
                        while time.time() < timeout_start + 600 and CloudfrontDomainName is None:
                            CloudfrontDomainName = get_cf_distribution_domain(dnsEntryName)

                        loadbalancersOfServices[ingressName] = {
                            'dnsEntryName': dnsEntryName,
                            'dnsEntryZone': dnsEntryZone,
                            'albAddress': ingressAddress,
                            'cdnAddress': CloudfrontDomainName,
                            'enablecdn': EnableCloudfront
                        }
                        if CloudfrontDomainName is not None:
                            logging.info(f"Creating Cloudfront dns record {dnsEntryName} pointing to {CloudfrontDomainName}")
                            route53.create_or_update_dns_record(region, dnsEntryZone, dnsEntryName, CloudfrontDomainName, addressType="Cloudfront")
                        else:
                            logging.warning(f"Unable to create Cloudfront dns record {dnsEntryName} bcz couldn't found any cloudfront with alias {dnsEntryName}")
            else:
                loadbalancersOfServices.pop(ingressName)

        # If the microservice/ingress-address key value pair has an update, add it to dict and update the DNS record
        elif ingressAddress != "" and loadbalancersOfServices[ingressName]['albAddress'] != ingressAddress:
            print("")
            logging.info(f"{ingressName}'s loadbalancer address has changed, so updating it's DNS record")
            dnsEntryName, dnsEntryZone = construct_dns_entry(ingressName, environment, region)

            loadbalancersOfServices[ingressName] = {
                'dnsEntryName': dnsEntryName,
                'dnsEntryZone': dnsEntryZone,
                'albAddress': ingressAddress,
                'enablecdn': EnableCloudfront
            }

            #EnableCloudfront = read_helm_enablecloudfront(ingressName)
            if dnsEntryName is not None:
                if deployCloudfront == "false" or EnableCloudfront == "false":
                    logging.info(f"Updating dns record {dnsEntryName} pointing to {ingressAddress}")
                    route53.create_or_update_dns_record(region, dnsEntryZone, dnsEntryName, ingressAddress, addressType="ALB")

                elif deployCloudfront == "true" and EnableCloudfront == "true":
                    dnsEntryNameOrigin = f"origin-{dnsEntryName}"
                    logging.info(f"Updating Cloudfront Origin dns record {dnsEntryNameOrigin} pointing to {ingressAddress}")
                    route53.create_or_update_dns_record(region, dnsEntryZone, dnsEntryNameOrigin, ingressAddress, addressType="ALB")

                    if regionActingAs == "master":

                        # Wait maximum of 10min to get the Cloudfront address
                        timeout_start = time.time()
                        CloudfrontDomainName = get_cf_distribution_domain(dnsEntryName)
                        while time.time() < timeout_start + 600 and CloudfrontDomainName is None:
                            CloudfrontDomainName = get_cf_distribution_domain(dnsEntryName)

                        loadbalancersOfServices[ingressName] = {
                            'dnsEntryName': dnsEntryName,
                            'dnsEntryZone': dnsEntryZone,
                            'albAddress': ingressAddress,
                            'cdnAddress': CloudfrontDomainName,
                            'enablecdn': EnableCloudfront
                        }
                        if CloudfrontDomainName is not None:
                            logging.info(f"Updating Cloudfront dns record {dnsEntryName} pointing to {CloudfrontDomainName}")
                            route53.create_or_update_dns_record(region, dnsEntryZone, dnsEntryName, CloudfrontDomainName, addressType="Cloudfront")
                        else:
                            logging.warning(f"Unable to update Cloudfront dns record {dnsEntryName} bcz couldn't found any cloudfront with alias {dnsEntryName}")
            else:
                loadbalancersOfServices.pop(ingressName)

        # If the microservice/EnableCloudfront key value pair has an update, add it to dict and update the DNS record
        elif ingressAddress != "" and ingressName in loadbalancersOfServices and loadbalancersOfServices[ingressName]['enablecdn'] != EnableCloudfront:
            print("")
            logging.info(f"{ingressName}'s enable cloudfront flag has changed to {EnableCloudfront}, so updating it's DNS record")
            dnsEntryName, dnsEntryZone = construct_dns_entry(ingressName, environment, region)

            loadbalancersOfServices[ingressName] = {
                'dnsEntryName': dnsEntryName,
                'dnsEntryZone': dnsEntryZone,
                'albAddress': ingressAddress,
                'enablecdn': EnableCloudfront
            }

            # EnableCloudfront = read_helm_enablecloudfront(ingressName)
            if dnsEntryName is not None:
                if deployCloudfront == "false" or EnableCloudfront == "false":
                    route53.delete_old_dns_record(region, dnsEntryZone, dnsEntryName, addressType="old-CNAME")
                    route53.delete_old_dns_record(region, dnsEntryZone, dnsEntryName, addressType="Cloudfront")
                    dnsEntryNameOrigin = f"origin-{dnsEntryName}"
                    route53.delete_old_dns_record(region, dnsEntryZone, dnsEntryNameOrigin, addressType="ALB")

                    logging.info(f"Updating dns record {dnsEntryName} pointing to {ingressAddress}")
                    route53.create_or_update_dns_record(region, dnsEntryZone, dnsEntryName, ingressAddress, addressType="ALB")

                elif deployCloudfront == "true" and EnableCloudfront == "true":
                    route53.delete_old_dns_record(region, dnsEntryZone, dnsEntryName, addressType="ALB")
                    route53.delete_old_dns_record(region, dnsEntryZone, dnsEntryName, addressType="old-CNAME")

                    dnsEntryNameOrigin = f"origin-{dnsEntryName}"
                    logging.info(f"Updating Cloudfront Origin dns record {dnsEntryNameOrigin} pointing to {ingressAddress}")
                    route53.create_or_update_dns_record(region, dnsEntryZone, dnsEntryNameOrigin, ingressAddress, addressType="ALB")

                    if regionActingAs == "master":

                        # Wait maximum of 10min to get the Cloudfront address
                        timeout_start = time.time()
                        CloudfrontDomainName = get_cf_distribution_domain(dnsEntryName)
                        while time.time() < timeout_start + 600 and CloudfrontDomainName is None:
                            CloudfrontDomainName = get_cf_distribution_domain(dnsEntryName)

                        loadbalancersOfServices[ingressName] = {
                            'dnsEntryName': dnsEntryName,
                            'dnsEntryZone': dnsEntryZone,
                            'albAddress': ingressAddress,
                            'cdnAddress': CloudfrontDomainName,
                            'enablecdn': EnableCloudfront
                        }
                        if CloudfrontDomainName is not None:
                            logging.info(f"Updating Cloudfront dns record {dnsEntryName} pointing to {CloudfrontDomainName}")
                            route53.create_or_update_dns_record(region, dnsEntryZone, dnsEntryName, CloudfrontDomainName, addressType="Cloudfront")
                        else:
                            logging.warning(f"Unable to update Cloudfront dns record {dnsEntryName} bcz couldn't found any cloudfront with alias {dnsEntryName}")
            else:
                loadbalancersOfServices.pop(ingressName)

    # If the microservice/ingress doesn't exists anymore, remove it from the dict and delete DNS record
    # https://stackoverflow.com/a/11941855
    for ingress in list(loadbalancersOfServices):
        if ingress not in microServicesList:
            print("")
            logging.info(f"{ingress}'s loadbalancer is deleted, so removing it's DNS record")

            dnsEntryName = loadbalancersOfServices[ingress]['dnsEntryName']
            dnsEntryZone = loadbalancersOfServices[ingress]['dnsEntryZone']
            EnableCloudfront = loadbalancersOfServices[ingress]['enablecdn']

            if dnsEntryName is not None:
                if deployCloudfront == "false" or EnableCloudfront == "false":
                    logging.info(f"Removing dns record {dnsEntryName} pointing to {loadbalancersOfServices[ingress]['albAddress']}")
                    route53.delete_dns_record(region, dnsEntryZone, dnsEntryName, loadbalancersOfServices[ingress]['albAddress'], addressType="ALB")

                elif deployCloudfront == "true" and EnableCloudfront == "true":
                    dnsEntryNameOrigin = f"origin-{dnsEntryName}"
                    logging.info(f"Removing Cloudfront Origin dns record {dnsEntryNameOrigin} pointing to {loadbalancersOfServices[ingress]['albAddress']}")
                    route53.delete_dns_record(region, dnsEntryZone, dnsEntryNameOrigin, loadbalancersOfServices[ingress]['albAddress'], addressType="ALB")

                    if regionActingAs == "master" and loadbalancersOfServices[ingress]['cdnAddress'] is not None:
                        logging.info(f"Removing Cloudfront dns record {dnsEntryName} pointing to {loadbalancersOfServices[ingress]['cdnAddress']}")
                        route53.delete_dns_record(region, dnsEntryZone, dnsEntryName, loadbalancersOfServices[ingress]['cdnAddress'], addressType="Cloudfront")

            loadbalancersOfServices.pop(ingress)

    time.sleep(30)
