#!/usr/bin/python

import argparse
import json
import logging
import os
import time
from operator import itemgetter
from typing import Dict

from bson import json_util
from lib.cloudformation_manager import CloudformationManager
from lib.core_components import AwsInfrastructureServiceDeployer
from lib.infrastructure_build_manager import InfrastructureBuildManager
from lib.s3 import S3Manager

ap = argparse.ArgumentParser()
ap.add_argument("--action", required=False,
                default="Deploy",
                help="Optional: Default is Deploy. Use Delete to tear down stack")
ap.add_argument("--envName", required=True, help="Required: Environment name equals environment to deploy to")
ap.add_argument("--gitHash", required=True, help="Required: Git branch hash for deployment distinction")

args = vars(ap.parse_args())

# Set main variables
action = args["action"]
env_name = args["envName"]
git_hash = args["gitHash"]

params_dir = f"./params/{env_name}/"
git_tag_file = f"./params/{env_name}/gittag.params"


def sync_s3(bucket, envName, prefix):
    # for nested stacks, the sub stack is called by url to an template in s3
    for filename in os.listdir("./cfn"):
        local_file = "./cfn/" + filename
        s3_file = envName + "/" + prefix + "/" + filename
        logging.info(f"Uploading to S3 us-east-1 {local_file} to {bucket}:{s3_file}")
        S3Manager.file_upload("us-east-1", local_file, bucket, s3_file)
        # file_upload("./cfn/" + filename, bucket, envName + "/" + prefix + "/" + filename)


def deployment_in_progress(regionsSortedList):
    in_progress = False
    all_regions_status_list = list(map(itemgetter("DeploymentStatus"), regionsSortedList))
    # print("DEBUGGING: Status of all regions are: " + str(allRegionsStatusList))

    for status in all_regions_status_list:
        if status != "DONE":
            in_progress = True
            break
    if in_progress:
        return True
    else:
        return False


def do_action():
    # Get build information for all the regions
    regions_sorted_list = InfrastructureBuildManager.prepare_region_builds(params_dir, env_name, git_hash, git_tag_file)
    regions_string = ", ".join(
        [f"{region['RegionName']} ({region['RegionActingAs']})" for region in regions_sorted_list]
    )

    logging.info("")
    logging.info(f"Deployment of {env_name} will be done in {regions_string} regions")
    logging.info("")

    # Loop through the list of regions and do the deployment of every region
    for region_dict in regions_sorted_list:
        # retrieve region build data and environment
        params = region_dict["Params"]
        service_deployers: Dict[str, AwsInfrastructureServiceDeployer] = region_dict["ServiceDeployers"]
        region_environment = region_dict["Environment"]

        # Just for debugging
        # print("")
        # print("Params of " + regionDict['RegionName'] + " (" + regionDict['RegionActingAs'] + ") region are: ")
        # for param in params:
        #     print("{:30s} {:s}".format(param['ParameterKey'] + ': ', param['ParameterValue']))

        print("")
        print(
            "Performing "
            + action
            + " operation for "
            + env_name
            + " env in "
            + region_dict["RegionName"]
            + " ("
            + region_dict["RegionActingAs"]
            + ") region"
        )

        # Actions to be able to run deployers steps out of the environment build
        if action == "pre_build":
            for service in service_deployers.keys():
                logging.info(f"PRE BUILD resources from deployer: {service}")
                service_deployers[service].pre_build()

        elif action == "post_build":
            for service in service_deployers.keys():
                logging.info(f"POST BUILD resources from deployer: {service}")
                service_deployers[service].post_build()

        elif action == "pre_delete":
            for service in service_deployers.keys():
                logging.info(f"PRE DELETE resources from deployer: {service}")
                service_deployers[service].pre_delete()

        elif action == "post_delete":
            for service in service_deployers.keys():
                logging.info(f"POST DELETE resources from deployer: {service}")
                service_deployers[service].post_delete()

        elif action == "Delete":
            # PRE DELETE
            for service in service_deployers.keys():
                logging.info(f"PRE DELETE resources from deployer: {service}")
                service_deployers[service].pre_delete()

            CloudformationManager.delete_stack(region_environment["Region"], region_environment["Name"])
            time.sleep(5)

            status = CloudformationManager.stack_status(region_environment["Region"], region_environment["Name"])

            print(region_environment["Region"] + " stack status: " + status)
            region_dict["DeploymentStatus"] = status

        else:
            # check if exists
            stack_name = CloudformationManager.stack_exist(region_environment["Region"], region_environment["Name"])

            template = (
                "https://s3.amazonaws.com/"
                + region_environment["Bucket"]
                + "/"
                + region_environment["Name"]
                + "/"
                + region_environment["DeployBucketPrefix"]
                + "/composite.template.yaml"
            )
            # build if stackName doesn't exist
            if stack_name is None:
                # upload templates to s3
                sync_s3(
                    region_environment["Bucket"], region_environment["Name"], region_environment["DeployBucketPrefix"]
                )

                # PRE BUILDS
                for service in service_deployers.keys():
                    logging.info(f"PRE BUILD resources from deployer: {service}")
                    service_deployers[service].pre_build()

                # launch build

                build = CloudformationManager.create_stack(
                    region_environment["Region"],
                    region_environment["Name"],
                    template,
                    params,
                    region_environment["EnvType"],
                )

                print(json.dumps(build, sort_keys=False, indent=4, default=json_util.default))

                time.sleep(5)
                status = CloudformationManager.stack_status(region_environment["Region"], region_environment["Name"])
                print(region_environment["Region"] + " stack status: " + status)
                region_dict["DeploymentStatus"] = status

                if status == "CREATE_FAILED":

                    details = CloudformationManager.describe_stacks(
                        region_environment["Region"], region_environment["Name"]
                    )
                    print(json.dumps(details, sort_keys=False, indent=4, default=json_util.default))
                    exit(1)

            # update if the stack exists
            elif stack_name is not None:

                status = CloudformationManager.stack_status(stack_name, region_environment["Name"])

                if status not in "DELETE_COMPLETE, DELETE_FAILED":
                    # upload templates to s3
                    sync_s3(
                        region_environment["Bucket"],
                        region_environment["Name"],
                        region_environment["DeployBucketPrefix"],
                    )

                    for service in service_deployers.keys():
                        logging.info(f"PRE UPDATE resources from deployer: {service}")
                        service_deployers[service].pre_update()

                    # launch build
                    build = CloudformationManager.update_stack(
                        region_environment["Region"], region_environment["Name"], template, params
                    )

                    print(json.dumps(build, sort_keys=False, indent=4, default=json_util.default))

                    time.sleep(5)
                    status = CloudformationManager.stack_status(
                        region_environment["Region"], region_environment["Name"]
                    )
                    print(region_environment["Region"] + " stack status: " + status)
                    region_dict["DeploymentStatus"] = status

    while deployment_in_progress(regions_sorted_list):

        # Loop through the list of regions and check the status on every region
        print("")
        for region_dict in regions_sorted_list:
            time.sleep(10)
            service_deployers: Dict[str, AwsInfrastructureServiceDeployer] = region_dict["ServiceDeployers"]
            # prepare params - need params from files
            environment = InfrastructureBuildManager.get_build_environment(
                region_dict["RegionName"], env_name, git_hash
            )

            status = CloudformationManager.stack_status(environment["Region"], environment["Name"])

            print(environment["Region"] + " stack status: " + status)

            if action == "Delete":
                if status in "DELETE_COMPLETE, DELETE_FAILED, DELETED":
                    region_dict["DeploymentStatus"] = "DONE"

                    if status in "DELETE_COMPLETE, DELETED":
                        for service in service_deployers.keys():
                            logging.info(f"POST DELETE [{service}]: {service}")
                            try:
                                service_deployers[service].post_delete()
                            except Exception as e:
                                logging.critical(f"POST DELETE ERROR [{service}]: {e}")
                else:
                    region_dict["DeploymentStatus"] = status

                if status == "DELETE_FAILED":
                    exit(1)

            else:
                if status == "CREATE_COMPLETE":
                    # details = stack_details(environment["Name"], environment["Region"])
                    # print(json.dumps(details, sort_keys = False, indent = 4, default = json_util.default))

                    region_dict["DeploymentStatus"] = "DONE"

                    # POST BUILDS
                    for service in service_deployers.keys():
                        logging.info(f"POST BUILD [{service}]: {service}")
                        try:
                            service_deployers[service].post_build()
                        except Exception as e:
                            logging.critical(f"POST BUILD ERROR [{service}]: {e}")

                elif status in "CREATE_FAILED UPDATE_ROLLBACK_COMPLETE":
                    print(environment["Region"] + " if condition of CREATE_FAILED")

                    details = CloudformationManager.describe_stacks(environment["Region"], environment["Name"])
                    print(json.dumps(details, sort_keys=False, indent=4, default=json_util.default))
                    exit(1)
                elif status not in "DELETE_COMPLETE, DELETE_FAILED":
                    if status == "UPDATE_COMPLETE":
                        # details = stack_details(environment["Name"], environment["Region"])
                        # print(json.dumps(details, sort_keys = False, indent = 4, default = json_util.default))
                        region_dict["DeploymentStatus"] = "DONE"

                        for service in service_deployers.keys():
                            logging.info(f"POST UPDATE [{service}]: {service}")
                            try:
                                service_deployers[service].post_update()
                            except Exception as e:
                                logging.critical(f"POST UPDATE ERROR [{service}]: {e}")
                else:
                    region_dict["DeploymentStatus"] = status


do_action()
