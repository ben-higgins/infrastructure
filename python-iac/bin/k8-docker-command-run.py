import argparse

from lib.region_manager import RegionManager
from lib.kubernetes_manager import KubernetesManager

ap = argparse.ArgumentParser()
ap.add_argument("--region", required=False, help="AWS region EKS was deployed to")
ap.add_argument("--environment", required=True, help="Environment to deploy to")
ap.add_argument("--service", required=True, help="Service to run")
ap.add_argument("--command", required=True, help="Command to run")

args = vars(ap.parse_args())

environment = args.get("environment")
region = args.get("region")
service = args.get("service")
command = args.get("command")

regions = RegionManager.get_regions(environment=environment, region=region)

successful_runs = []
unsuccessful_runs = []

# Loop through the list of regions and perform the command on every region
for region in regions:

    print(f"\nREGION {region}")
    print("Get EKS Cluster Name")
    cluster_name = KubernetesManager.get_cluster(environment, region)

    if not cluster_name:
        unsuccessful_runs.append((environment, region))

        print(f"No EKS cluster named {environment} found in region {region}\n", flush=True)

        continue

    print(f"Performing command operation for {environment} env in {region} region", flush=True)

    kubernetes_manager = KubernetesManager(cluster_name, region)
    pods = kubernetes_manager.get_pods()

    service_pod = None

    for pod_name, pod_namespace, pod_status in pods:
        if service in pod_name and pod_status == "Running":
            service_pod = (pod_name, pod_namespace)
            break
    else:
        unsuccessful_runs.append((environment, region))

        print(f"No {service} pod in environment {environment} and region {region}\n", flush=True)

        continue

    print(f'Executing: {command}', flush=True)
    response = kubernetes_manager.execute_command(service_pod[0], service_pod[1], ['/bin/bash', '-c', command])

    if response:
        successful_runs.append((environment, region))

        print(response, flush=True)
        print(f"Done running command environment {environment} and region {region}!\n", flush=True)
    else:
        unsuccessful_runs.append((environment, region))

print(f"\n\nSummary:\n- Successful runs: {successful_runs}\n- Unsuccessful runs:{unsuccessful_runs}\n")

if unsuccessful_runs:
    exit(1)
