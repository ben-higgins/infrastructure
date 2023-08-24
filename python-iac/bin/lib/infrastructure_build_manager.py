import copy
import os
from operator import itemgetter
from typing import Dict, Optional

from .cloudformation_manager import CloudformationManager
from .core_components import AwsInfrastructureServiceDeployer
from .ec2 import EC2Manager
from .logger import logging
from .mwaa import MwaaAwsInfrastructureServiceDeployer
from .redshift import RedshiftAwsInfrastructureServiceDeployer


class InfrastructureBuildManager:
    @classmethod
    def read_gittag_param(cls, git_tag_file: str):
        with open(git_tag_file) as file:
            for line in file:
                if line.strip() and not line.startswith("#"):
                    linesplit = line.split(":", 1)
                    gittag = linesplit[1].strip()
        return gittag

    @classmethod
    def build_params(
        cls,
        environment_name: str,
        git_hash: str,
        region: str,
        environment: Dict[str, str],
        service_deployers: Dict[str, AwsInfrastructureServiceDeployer] = {},
        git_tag_file: Optional[str] = None,
    ):

        logging.info(f"Setting Cloudformation parameters for: {environment_name}/{region}")
        params = [
            {"ParameterKey": key, "ParameterValue": environment[key]}
            for key in environment.keys()
            if not key.startswith("SYS_")
        ]

        # git param was moved outside of region directory so need to pull in separately for now
        tag = None
        if git_tag_file:
            tag = cls.read_gittag_param(git_tag_file)
        params.append({"ParameterKey": "GitTag", "ParameterValue": tag})

        # append params that are injected
        params.append({"ParameterKey": "DeployBucketPrefix", "ParameterValue": git_hash})
        params.append({"ParameterKey": "Name", "ParameterValue": environment_name})
        params.append({"ParameterKey": "Region", "ParameterValue": region})

        # get transit gateway id for region
        transit_gateway_id = EC2Manager.get_transit_gateway_id(region)
        params.append({"ParameterKey": "TransitGatewayId", "ParameterValue": transit_gateway_id})

        # Extract redshift cluster ID from params
        # https://stackoverflow.com/a/7079297
        # RedshiftEnvType = next((item for item in params if item['ParameterKey'] == 'EnvType'), None)
        # RedshiftClusterEnv = RedshiftEnvType['ParameterValue']

        stack_name = CloudformationManager.stack_exist(region, environment_name)

        if stack_name is None:
            for service in service_deployers.keys():
                logging.info(f"Setting params from deployer: {service}")
                params = service_deployers[service].build_params(params)

        else:
            for service in service_deployers.keys():
                logging.info(f"Setting params from deployer: {service} in stack: {stack_name}")
                params = service_deployers[service].build_params_for_stack(stack_name, params)

        return params

    @classmethod
    def get_build_environment(
        cls, region: str, environment_name: str, git_hash: Optional[str] = None
    ) -> Dict[str, str]:
        logging.info(f"Setting environment for: {environment_name}/{region}")
        __env = dict(copy.deepcopy(os.environ))
        _build_env = {f"SYS_{key}": __env[key] for key in __env.keys()}
        dir = "./params/" + environment_name + "/" + region + "/"
        for filename in os.listdir(dir):
            try:
                file = open(dir + filename)
                for line in file:
                    if line.strip() and not line.startswith("#"):
                        linesplit = line.split(":", 1)
                        _build_env[linesplit[0].strip()] = linesplit[1].strip()
            finally:
                file.close()

        _build_env["DeployBucketPrefix"] = git_hash
        _build_env["Name"] = environment_name
        _build_env["Region"] = region

        return _build_env

    @classmethod
    def prepare_region_builds(
        cls, params_dir: str, env_name: str, git_hash: Optional[str] = None, git_tag_file: Optional[str] = None
    ):
        """
        Returns a sorted list objects by RegionActingAs object field where "master" region will be the first one and "slave" after that
        """
        regions = [name for name in os.listdir(params_dir) if os.path.isdir(os.path.join(params_dir, name))]

        # Loop through the list of regions and create a list of dictionaries that will be sorted in next step
        regions_list = []
        for region in regions:
            service_deployers = {}
            # prepare environment first
            environment = InfrastructureBuildManager.get_build_environment(region, env_name, git_hash)

            # prepare deployers based on environment
            if environment["DeployMWAA"] == "true":
                service_deployers["mwaa"] = MwaaAwsInfrastructureServiceDeployer(env_name, region, environment)

            if environment["DeployRedshift"] == "true":
                service_deployers["redshift"] = RedshiftAwsInfrastructureServiceDeployer(env_name, region, environment)

            # set cloudformation parameters

            params = InfrastructureBuildManager.build_params(
                env_name, git_hash, region, environment, service_deployers, git_tag_file
            )

            # create region dict
            regions_list.append(
                {
                    "EnvName": env_name,
                    "RegionName": region,
                    "DeploymentStatus": "",
                    "RegionActingAs": environment["RegionActingAs"],
                    "Params": params,
                    "Environment": environment,
                    "ServiceDeployers": service_deployers,
                }
            )

        # Sort the list of regions based on their Master/Slave status, slave region will come up first in the list
        # regionsSortedList = (sorted(regionsList, key=itemgetter('RegionActingAs'), reverse = True))
        # Sort the list of regions based on their Master/Slave status, master region will come up first in the list
        return sorted(regions_list, key=itemgetter("RegionActingAs"))
