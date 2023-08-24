import argparse
from lib.kubernetes_manager import KubernetesManager
from lib.region_manager import RegionManager
from lib.secrets_manager import ServiceSecretManager

ap = argparse.ArgumentParser()
ap.add_argument("--develop", action="store_true", help="Seed Develop?")
ap.add_argument("--testing", action="store_true", help="Seed Testing?")
ap.add_argument("--main", action="store_true", help="Seed Main?")
args = vars(ap.parse_args())

develop = args.get("develop")
testing = args.get("testing")
main = args.get("main")
COMMAND = ["/bin/bash", "-c", "python -m tools.company_products_seeding"]
ENVS = []
if develop:
    print(f"\nUsing Develop...", flush=True)
    ENVS.append("develop")
if testing:
    print(f"\nUsing Testing...", flush=True)
    ENVS.append("testing")
if main:
    print(f"\nUsing Main...", flush=True)
    ENVS.append("main")

print(f"\nStarting seeding job...", flush=True)
failed_env_regions = []
for env in ENVS:
    print(f"\nGetting regions... for {env}", flush=True)

    REGIONS = RegionManager.get_regions(env)
    for region in REGIONS:
        print(f"\nGet EKS Cluster Name for {env} and {region}", flush=True)
        cluster_name = KubernetesManager.get_cluster(env, region)

        if not cluster_name:
            print(f"No EKS cluster named {env} found in region {region}\n", flush=True)
            failed_env_regions.append(f"{env}-{region}")
            continue

        kubernetes_manager = KubernetesManager(cluster_name, region)
        pods = kubernetes_manager.get_pods()

        reptrak_user_management_pod = None

        for pod_name, pod_namespace, pod_status in pods:
            if "reptrak-user-management" in pod_name and pod_status == "Running":
                reptrak_user_management_pod = (pod_name, pod_namespace)
                break
        else:
            print(f"No reptrak_user_management pod found\n", flush=True)
            continue

        try:
            print(f"Running seeding for {env} in region {region}\n", flush=True)
            response = kubernetes_manager.execute_command(reptrak_user_management_pod[0], reptrak_user_management_pod[1], COMMAND)
            if response:
                print(response, flush=True)
                print(f"Done seeding environment {env} and region {region}!\n", flush=True)
            else:
                failed_env_regions.append(f"{env}-{region}")
        except Exception as e:
            print(f"Error while executing seeding command in reptrak-user-management: {e}", flush=True)
            continue

for fail in failed_env_regions:
    print(f"{fail} env/region failed to find clusters")

print(f"Done seeding environment account core products!\n", flush=True)