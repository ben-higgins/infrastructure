import argparse
import json
import os
import time
import lib.params as parameters
from typing import Tuple

import lib.exec_ctl as exe
import yaml
from docker.errors import APIError, BuildError
from lib.cloudformation_manager import CloudformationManager
from lib.docker_manager import DockerManager
from lib.ecr_manager import EcrManager
from lib.kubernetes_manager import KubernetesManager
from lib.logger import logging
from lib.region_manager import RegionManager
from lib.secrets_manager import ServiceSecretManager

DockerManager.debug = True
# logging.getLogger().setLevel(logging.DEBUG)

ap = argparse.ArgumentParser()
ap.add_argument(
    "--action",
    required=True,
    choices=["Deploy", "Rollback", "Delete", "Build"],
)

ap.add_argument(
    "--deployRegion",
    required=False,
    help="AWS region EKS was deployed to"
)

ap.add_argument(
    "--jobName",
    required=True,
    help="Name of Application being deployed"
)

ap.add_argument(
    "--buildNumber",
    required=False,
    default="1",
    help="Container build number taken from Jenkins build number",
)

ap.add_argument("--branchName", required=True, help="Branch to deploy from")

ap.add_argument(
    "--environment",
    required=False,
    help="Environment to deploy to, if missing brachName is used",
)
ap.add_argument("--helmParams", required=False, help="List of additional params for helm")

args = vars(ap.parse_args())

# build number is not required
build_number = args["buildNumber"]


def parse_branch_name(branch_raw):
    # value might come in with a prefix
    if branch_raw.find("/") != -1:
        branch = branch_raw.split("/")[-1]
    else:
        branch = branch_raw
    return branch


def set_envtype(branch_raw):

    branch = parse_branch_name(branch_raw)

    # TODO: temporary workaround to assign an environment type of develop
    # if deploying a feature branch

    if branch not in ["develop", "qa", "main"]:
        env_type = "testing"
    else:
        env_type = branch

    return env_type


def helm_rollback(job_name):
    # check if first revisioned failed
    command = "/usr/local/bin/helm rollback " + job_name + " 0"
    output = exe.sub_process(command.split())
    logging.info(output)


def helm_delete(job_name):
    command = "/usr/local/bin/helm delete " + job_name
    output = exe.sub_process(command.split())
    logging.info(output)


def container_build(
    environment, job_name, region, build_number
):
    # https://docker-py.readthedocs.io/en/stable/
    container = f"{environment}-{job_name}"
    tag = f"{container}:{build_number}"
    latest = f"{container}:latest"

    logging.info("Step 4.a: Check if repository already exists in ECR")
    if not EcrManager.registry_exists(container, region):
        EcrManager.create_registry(container, region)

    logging.info("Step 4.b: Build container")

    logging.debug("Creating build args")
    default_buildargs = {"BUILD_NUMBER": build_number}

    buildargs = default_buildargs.copy()

    try:
        path = os.path.realpath("./../" + job_name)
        image = DockerManager.build_image(path, tag, buildargs=buildargs)
    except BuildError as e:
        logging.info("BuildError Building container")
        logging.info(e, e.msg, e.build_log, e.__traceback__.__str__())
        exit(1)
    except APIError as e:
        logging.info("APIError Building container")
        logging.info(e, e.response, e.explanation, e.__traceback__.__str__())
        exit(1)
    except TypeError as e:
        logging.info("TypeError Building container")
        logging.info(e, e.__traceback__.__str__())
        exit(1)
    except Exception as e:
        logging.info("Exception Building container")
        logging.info(e, e.__traceback__.__str__())
        exit(1)

    logging.info("Step 4.c: ECR Authentication")
    ecr_username, ecr_password, ecr_url = EcrManager.get_erc_credentials(region)
    # get Docker to login/authenticate with ECR
    DockerManager.login(ecr_username, ecr_password, ecr_url)
    # docker_client.login(username=ecr_username, password=ecr_password, registry=ecr_url)

    # tag image for AWS ECR
    tags = {latest, tag}
    auth_config = {
        "username": ecr_username,
        "password": ecr_password,
    }

    for t in tags:
        logging.info("Step 4.d: Tag container image")
        ecr_repo_name = "{}/{}".format(ecr_url.replace("https://", ""), t)
        # tag local docker image
        image.tag(ecr_repo_name)
        # push image to AWS ECR
        logging.info("Step 4.e: Push container to ECR rep: " + ecr_repo_name)
        DockerManager.push_image(ecr_repo_name, auth_config)
        # push_log = docker_client.images.push(ecr_repo_name, auth_config=auth_config)
        # logging.info(push_log)

    # return the non-latest tag value
    return "{}/{}".format(ecr_url.replace("https://", ""), tag)

def create_configmap(environment, job_name, region):
    logging.info(
        f"Creating configmap for branch {environment} "
        f"for the job {job_name}, on the region {region}"
    )

    try:
        set_params = get_service_secrets(
            environment, job_name, region
        )
    except Exception as e:
        logging.critical(f"Continuing the deployment wihout creating configmap: {e}")
        return


    logging.info(".env content")
    logging.info(set_params[1])
    configmap_raw = {
        "kind": "ConfigMap",
        "apiVersion": "v1",
        "metadata": {"name": job_name + "-env"},
        "data": {".env": set_params[1]},
    }

    configmap = yaml.dump(configmap_raw)

    f = open("./bin/configmap.yaml", "w")
    f.write(configmap.replace("'", ""))
    f.close()

    command = "kubectl apply -f ./bin/configmap.yaml"
    exe.sub_process(command.split())


def get_service_secrets(environment, job_name, region) -> Tuple[dict, str]:
    helm = open("../" + job_name + "/.helm/deployment_chart/values.yaml", "rb").read()

    secrets = {
        "ENV": environment,
        "REGION": region,
    }

    service_secrets = ServiceSecretManager.get_secret(
        region, f"{environment}/{job_name}", json_decode=True)

    services_infra_secrets = ServiceSecretManager.provision_helm(helm, environment, region)

    full_secrets = {**service_secrets, **secrets, **services_infra_secrets}

    return (full_secrets, ServiceSecretManager.dict_to_dotenv_lines(full_secrets))



def deploy_helm(docker_container, job_name, environment, region, cluster_name):
    # check if first revisioned failed
    command = "/usr/local/bin/helm history " + job_name + " --max 1 --output json"
    chart_status_raw = exe.sub_process(command.split())

    # if helm template kind is job then delete the previous deployment
    list = os.listdir(f"../{job_name}/.helm/deployment_chart/templates")
    for file in list:
        helm_values = open(f"../{job_name}/.helm/deployment_chart/templates/{file}").read()
        result = helm_values.find("kind: Job")

    try:
        chart_json = json.loads(chart_status_raw)
    except Exception:
        logging.info("Deployment doesn't exist yet")

    else:
        # This condition fails the deployment for previously failed helm chart
        # if chart_json[0]["revision"] == 1:
        if chart_json[0]["status"] == "FAILED" or result != -1:
            command = "/usr/local/bin/helm delete " + job_name

            check_exists = exe.sub_process(command.split())
            logging.info("checkExists: " + str(check_exists))

            # make sure helm finishes deleting before moving on
            while "Error" in check_exists:
                time.sleep(5)
                check_exists = exe.sub_process(command.split())
                logging.info("checkExists: " + str(check_exists))

    params = ""
    helm_values = open(
        f"../{job_name}/.helm/deployment_chart/values.yaml"
    ).read()

    # check if RegionActingAs exists in values.yaml,
    # that means helm chart needs to deploy cron job in single region
    result = helm_values.find('RegionActingAs')
    if result != -1:
        logging.info(
            "Found Single Region deployment requirement of cron in helm: "
            + f"{environment} {region}"
        )

        # Read value for RegionActingAs from region's params directory
        parameters.load_params_mem(environment, region)
        RegionActingAs = os.environ["RegionActingAs"]

        if RegionActingAs is not None:
            params = params + " --set RegionActingAs=" + RegionActingAs
        else:
            logging.info("Failed to retrieve RegionActingAs from params")
            logging.info("Continuing deployment without RegionActingAs")

    # check if DeployCloudfront exists in values.yaml,
    # that means helm chart needs to deploy cron job in single region
    result = helm_values.find('DeployCloudfront')
    if result != -1:
        logging.info(
            "Found Cloudfront deployment requirement in helm: "
            + f"{environment} {region}"
        )

        # Read value for DeployCloudfront from region's params directory
        parameters.load_params_mem(environment, region)
        DeployCloudfront = os.environ["DeployCloudfront"]

        if DeployCloudfront is not None:
            params = params + " --set DeployCloudfront=" + DeployCloudfront
        else:
            logging.info("Failed to retrieve DeployCloudfront from params")
            logging.info("Continuing deployment without DeployCloudfront")

    command = (
        "/usr/local/bin/helm upgrade --install "
        + params
        + " --set region="
        + region
        + " --set container.image="
        + docker_container
        + " --set serviceName="
        + job_name
        + " --set envType="
        + environment
        + " --set volumeMount.name="
        + job_name
        + "-env"
        + " --wait --timeout 10m0s "
        + job_name
        + " ../"
        + job_name
        + "/.helm/deployment_chart"
    )
    return_code, output = exe.sub_process_rc(command.split())
    logging.info(output)

    if return_code != 0:
        logging.info("Error: helm install command failed")
        exit(1)


def action(
    branch_name, cluster_name, region, job_name, action, build_number, environment=None,):

    # update-kubeconfig to connect to right cluster
    logging.info("Step 3: Update kubectl config with EKS Cluster Details")
    KubernetesManager.update_kubeconfig(cluster_name, region)

    docker_container = None

    if action == "Build" or action == "Deploy":
        # build container
        logging.info("Step 4: Build container")
        docker_container = container_build(
            environment,
            job_name,
            region,
            build_number,
        )

    if action == "Deploy" and docker_container is not None:
        # create env configmap
        logging.info(f"Step 5: Create ENV configmap for branch {branch_name}")
        create_configmap(environment, job_name, region)

        # deploy helm charts
        logging.info("Step 5: Deploy helm chart")
        deploy_helm(
            docker_container, job_name,
            environment, region, cluster_name
        )

    elif action == "Rollback":
        # deploy helm charts
        logging.info("Step 4: Rollback helm chart")
        helm_rollback(job_name)

    elif action == "Delete":
        helm_delete(job_name)


# check overrides
logging.info("Step 1a: Select environment")

branch_name = args.get("branchName")
environment = args.get("environment")

branch_name = parse_branch_name(branch_name)

if not environment:
    environment = branch_name


# Create a list of all regions of the env
regions = RegionManager.get_regions(
    environment=environment, region=args["deployRegion"])

if not regions:
    logging.info("No region was supplied")
    exit(1)

logging.info(
    f"branch_name: {branch_name} environment: {environment} selected regions are "
    + ", ".join(regions)
)

# Loop through the list of regions and perform the selected action on every region
for region in regions:

    logging.info("Step 2: Get EKS Cluster Name")
    cluster_name = CloudformationManager.get_service_stack_name(region, environment, "Eks")

    logging.info(f"Performing {args['action']} operation for {environment} env in {region} region")
    logging.info("")
    action(
        branch_name,
        cluster_name,
        region,
        args["jobName"],
        args["action"],
        build_number,
        environment
    )
