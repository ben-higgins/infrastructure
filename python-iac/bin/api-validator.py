
import requests
import os
import argparse
from lib.region_manager import RegionManager
from lib.kubernetes_manager import KubernetesManager

parser = argparse.ArgumentParser()
parser.add_argument('--region',  nargs='?', const='', help='Secrets manager destination region')
parser.add_argument('--envName', help='Destination environment prefix name')
parser.add_argument('--routes', help='List of routes to test')
args = parser.parse_args()


# region override
if args.region:
    regions = [args.region]
else:
    # Create a list of all regions of the env
    regions = RegionManager.get_regions(
        environment=args.envName, region="None")

# loop over regions to gets
for region in regions:

    print(f'environment region: {region}')
    # connect to correct cluster
    cluster_name = KubernetesManager.get_cluster(args.envName, region)
    # cluster_name = CloudformationManager.get_service_stack_name(region, args.envName, "Eks")
    KubernetesManager.update_kubeconfig(cluster_name, region)

    # retrieve gateway-proxy aws ALB address
    gateway = KubernetesManager.get_service_url("gateway-proxy")

    # loop over list of api endpoints
    routes = args.routes.split()
    failed = []
    for route in routes:
        print(f'Checking: https://{gateway}{route}')
        try:
            r = requests.get(f'https://{gateway}{route}', verify=False)

        except e:
            print(f'Failed to call https://{gateway}{route}. Error: {e}')

        if r.status_code != 200:
            failed.append(f'FAILED: https://{gateway}{route} - {r.status_code}')


    if len(failed) != 0:
        print("\n\nThe following endpoints failed")
        for f in failed:
            print(f)

        exit(1)
    else:
        print("No errors")

