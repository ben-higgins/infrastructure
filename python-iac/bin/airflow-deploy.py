#!/usr/bin/python

import argparse
import time

import lib.mwaa as mwaa
from lib.infrastructure_build_manager import InfrastructureBuildManager
from lib.logger import logging
from lib.s3 import S3Manager

ap = argparse.ArgumentParser()
ap.add_argument("--action", required=True, default="Deploy", help="Required: set the action to trigger")
ap.add_argument("--gitBranch", required=True, default="develop", help="Required: Branch code to sync remote")
ap.add_argument("--envName", required=True, help="Required: Environment name equals environment to deploy to")
ap.add_argument("--kms_key_arn", required=False, help="KMS key arn. Neccesary for decrypting")
ap.add_argument("--cleanupRepo", default="true", required=False, help="Clean the local repo before pull the code")
ap.add_argument(
    "--force_airflow_env_update", default="false", required=False, help="Clean the local repo before pull the code"
)
ap.add_argument(
    "--watchIfUnavailable", default="true", required=False, help="Clean the local repo before pull the code"
)

args = vars(ap.parse_args())

action = args["action"]
env_name = args["envName"]
branch = args["gitBranch"]
kms_key_arn = args["kms_key_arn"]
cleanup_repo = True if args["cleanupRepo"] == "true" else False
watch_if_unavailable = True if args["watchIfUnavailable"] == "true" else False
force_airflow_env_update = True if args["force_airflow_env_update"] == "true" else False

params_dir = f"./params/{env_name}/"


def do_action():
    logging.info(f"Running {action.upper()} {env_name} with branch: {branch}")
    # Get build information for all the regions
    regions_sorted_list = InfrastructureBuildManager.prepare_region_builds(params_dir, env_name)
    regions_string = ", ".join(
        [f"{region['RegionName']} ({region['RegionActingAs']})" for region in regions_sorted_list]
    )

    logging.info("")
    logging.info(f"Deployment of {env_name} will be done in {regions_string} regions")
    logging.info("")

    mwaa.MwaaCodeDeployer.clone_repository(branch, cleanup=cleanup_repo)

    master_region = regions_sorted_list[0]["RegionName"]
    # Loop through the list of regions and do the deployment of every region
    for region_dict in regions_sorted_list:
        # retrieve region build data and environment
        region_acting_as = region_dict["RegionActingAs"]

        region_environment = region_dict["Environment"]
        _region = region_environment["Region"]
        airflow_stack_info = mwaa.MwaaManager.get_airflow_environment_information(_region, env_name)

        airflow_operational_bucket = airflow_stack_info["operational_bucket"]
        airflow_source_code_bucket = airflow_stack_info["source_code_bucket"]
        airflow_environment_name = airflow_stack_info["infrastructure_environment_name"]
        airflow_stack_name = airflow_stack_info["stack_name"]

        current_status = mwaa.MwaaManager.get_airflow_status(_region, airflow_environment_name)

        if current_status != "AVAILABLE":
            logging.warning(f"Environment not available, please try later. Current status: {current_status}")
            if watch_if_unavailable:
                while current_status != "AVAILABLE":
                    logging.info(f"Environment unavailable... Current status {current_status}")
                    time.sleep(5)
                    response = mwaa.MwaaManager.get_environment(_region, airflow_environment_name)

                    current_status = response["Environment"]["Status"]

        if args["action"] in ["Setup", "Deploy"] and region_acting_as == "master":
            mwaa.MwaaManager.setup_k8_config(_region, airflow_source_code_bucket, env_name)

        if args["action"] == "Deploy":
            if region_acting_as != "master":
                mwaa.MwaaCodeDeployer.import_services_secrets_as_variables(
                    _region, master_region, airflow_stack_name, env_name, prefix_region=True
                )

                mwaa.MwaaCodeDeployer.import_remote_variables_reference(
                    _region, airflow_stack_name, airflow_environment_name, airflow_operational_bucket, env_name
                )

                continue

            logging.info("Importing local variables")
            mwaa.MwaaCodeDeployer.import_local_variables(_region, airflow_environment_name, env_name, kms_key_arn)

            logging.info("Importing infra services secrets for airflow")
            mwaa.MwaaCodeDeployer.import_services_secrets_as_variables(
                _region, master_region, airflow_stack_name, env_name, prefix_region=True
            )

            logging.info("Importing Custom Backend variables and connections references to normal airflow database")
            mwaa.MwaaCodeDeployer.import_remote_variables_reference(
                _region, airflow_stack_name, airflow_environment_name, airflow_operational_bucket, env_name
            )

            mwaa.MwaaCodeDeployer.sync_dags(_region, airflow_source_code_bucket)
            has_requirements_changed = mwaa.MwaaCodeDeployer.deploy_requirements(_region, airflow_source_code_bucket)
            has_plugins_changed = mwaa.MwaaCodeDeployer.deploy_plugins(_region, airflow_source_code_bucket)

            update_env = has_requirements_changed or has_plugins_changed or force_airflow_env_update
            log_msg = f"Performing environment update Force: {force_airflow_env_update}"
            if not update_env:
                log_msg = f"Environment update skip because dags/requirements.txt and plugins folder are sync. Force: {force_airflow_env_update}"
            logging.info(log_msg)

            if update_env:
                update_args = {
                    "region": _region,
                    "airflow_environment_name": airflow_environment_name,
                }
                if has_plugins_changed or force_airflow_env_update:
                    # plugins
                    versions = S3Manager.list_object_versions(_region, airflow_source_code_bucket, "plugins")

                    for version in versions:
                        version_id = version["VersionId"]
                        file_key = version["Key"]
                        file_is_latest = version["IsLatest"]

                        if file_key == "plugins.zip" and file_is_latest:
                            update_args["plugins_version"] = version_id

                if has_requirements_changed or force_airflow_env_update:
                    # requirements
                    versions = S3Manager.list_object_versions(_region, airflow_source_code_bucket, "dags/requirements")

                    for version in versions:
                        version_id = version["VersionId"]
                        file_key = version["Key"]
                        file_is_latest = version["IsLatest"]

                        if file_key == "dags/requirements.txt" and file_is_latest:
                            update_args["requirements_version"] = version_id

                logging.info(f"Updating environment: {update_args}")
                mwaa.MwaaManager.update_environment(**update_args)

    exit(0)


do_action()
