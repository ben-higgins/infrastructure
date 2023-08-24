import argparse

from lib.kubernetes_manager import KubernetesManager
from lib.region_manager import RegionManager
from lib.secrets_manager import ServiceSecretManager

ap = argparse.ArgumentParser()
ap.add_argument("--secondary_dbs", action="store_true", help="Seed secondary DBs?")
args = vars(ap.parse_args())

seed_secondary_dbs = args.get("secondary_dbs")

PRODUCTION_ENV = "main"

print(f"Getting main region...\n", flush=True)

PRODUCTION_REGION = RegionManager.get_regions(PRODUCTION_ENV)[0]

print(f"Getting Codebook secrets for main...\n", flush=True)

prod_secrets = ServiceSecretManager._fetch_mysql_secret(PRODUCTION_ENV, PRODUCTION_REGION)

try:
    main_codebook_url = f'mysql+pymysql://{prod_secrets["MYSQL_USER"]}:{prod_secrets["MYSQL_PASSWORD"]}@{prod_secrets["MYSQL_HOST"]}:{prod_secrets["MYSQL_PORT"]}/codebook'
except KeyError as e:
    print(f"Error fetching codebook credentials: {e}\n", flush=True)
    exit(1)

other_codebook_urls = []

if seed_secondary_dbs:
    print(f"Getting secondary dbs environments and regions...\n", flush=True)
    OTHER_ENVS = ["develop", "testing"]
    OTHER_REGIONS = [RegionManager.get_regions(env)[0] for env in OTHER_ENVS]

    other_secrets = [
        ServiceSecretManager._fetch_mysql_secret(env, region) for env, region in zip(OTHER_ENVS, OTHER_REGIONS)
    ]

    try:
        other_codebook_urls = [
            f'mysql+pymysql://{secrets["MYSQL_USER"]}:{secrets["MYSQL_PASSWORD"]}@{secrets["MYSQL_HOST"]}:{secrets["MYSQL_PORT"]}/codebook'
            for secrets in other_secrets
        ]
    except KeyError as e:
        print(f"Error fetching codebook credentials for other environments: {e}\n", flush=True)

other_dbs = " ".join([f"--secondary_db {url}" for url in other_codebook_urls])

COMMAND = ["/bin/bash", "-c", f"python -m tools.slugify_companies --main_db {main_codebook_url} {other_dbs}"]

print(COMMAND, flush=True)

print(f"Starting seeding job...\n", flush=True)

print("Get EKS Cluster Name", flush=True)
cluster_name = KubernetesManager.get_cluster(PRODUCTION_ENV, PRODUCTION_REGION)

if not cluster_name:
    print(f"No EKS cluster named {PRODUCTION_ENV} found in region {PRODUCTION_REGION}\n", flush=True)
    exit(1)

kubernetes_manager = KubernetesManager(cluster_name, PRODUCTION_REGION)
pods = kubernetes_manager.get_pods()

reptrak_user_management_pod = None

for pod_name, pod_namespace, pod_status in pods:
    if "reptrak-user-management" in pod_name and pod_status == "Running":
        reptrak_user_management_pod = (pod_name, pod_namespace)
        break
else:
    print(f"No reptrak_user_management pod found\n", flush=True)
    exit(1)

try:
    response = kubernetes_manager.execute_command(
        reptrak_user_management_pod[0], reptrak_user_management_pod[1], COMMAND
    )
    print(response)
except Exception as e:
    print(f"Error while executing seeding command in reptrak-user-management: {e}", flush=True)
    exit(1)

print(f"Done seeding environment codebook slugs!\n", flush=True)
