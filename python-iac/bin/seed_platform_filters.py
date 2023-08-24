import argparse

from lib.region_manager import RegionManager
from lib.kubernetes_manager import KubernetesManager


COMMAND = ["/bin/bash", "-c", "pip install psycopg2 mongoengine tqdm && python -m scripts.seed_db_and_cache"]

ap = argparse.ArgumentParser()
ap.add_argument("--region", required=False, help="AWS region EKS was deployed to")
ap.add_argument("--environment", required=True, help="Environment to deploy to")
args = vars(ap.parse_args())


environment = args.get("environment")
region = args.get("region")

regions = RegionManager.get_regions(environment=environment, region=region)

successful_seeds = []
unsuccessful_seeds = []


print(
    f"\nStarting seeding job for {environment} environment, selected regions are {', '.join(regions)}\n",
    flush=True,
)

# Loop through the list of regions and perform the seeding on every region
for region in regions:

    print(f"\nREGION {region}")
    print("Get EKS Cluster Name")
    cluster_name = KubernetesManager.get_cluster(environment, region)

    if not cluster_name:
        unsuccessful_seeds.append((environment, region))

        print(f"No EKS cluster named {environment} found in region {region}\n", flush=True)

        continue

    print(f"Performing seeding operation for {environment} env in {region} region", flush=True)

    kubernetes_manager = KubernetesManager(cluster_name, region)
    pods = kubernetes_manager.get_pods()

    platform_filters_pod = None

    for pod_name, pod_namespace, pod_status in pods:
        if "platform-filters" in pod_name and pod_status == "Running":
            platform_filters_pod = (pod_name, pod_namespace)
            break
    else:
        unsuccessful_seeds.append((environment, region))

        print(f"No platform-filters pod in environment {environment} and region {region}\n", flush=True)

        continue

    response = kubernetes_manager.execute_command(platform_filters_pod[0], platform_filters_pod[1], COMMAND)

    if response:
        successful_seeds.append((environment, region))

        print(response, flush=True)
        print(f"Done seeding environment {environment} and region {region}!\n", flush=True)
    else:
        unsuccessful_seeds.append((environment, region))

print(f"\n\nSummary:\n- Successful seeds: {successful_seeds}\n- Unsuccessful seeds:{unsuccessful_seeds}\n")

if unsuccessful_seeds:
    exit(1)
