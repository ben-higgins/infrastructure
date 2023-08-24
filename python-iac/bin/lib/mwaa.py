import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional
from zipfile import ZipFile

import lib.cloudformation as cloudformation
import lib.exec_ctl as exe
import requests
from git import GitCommandError, Repo

from .cloudformation_manager import CloudformationManager
from .core_components import AwsInfrastructureServiceDeployer, AwsServiceManager
from .ecr_manager import EcrManager
from .encryption_manager import EncryptionManager
from .logger import logging
from .s3 import S3Manager
from .secrets_manager import SecretManager, ServiceSecretManager

dirname, filename = os.path.split(os.path.abspath(__file__))
AIRFLOW_GIT_REPOSITORY_LOCAL_DEST = f"{dirname}/../../dbeng-airflow"
VERSIONS_FILE = f"{dirname}/../../airflow-requirements-plugins-s3-versions.json"


class MwaaManager(AwsServiceManager):
    service = "mwaa"

    @classmethod
    def create_cli_token(cls, region: str, airflow_environment_name: str):
        client = cls.get_client(region)
        return client.create_cli_token(Name=airflow_environment_name)

    @classmethod
    def update_environment(
            cls,
            region: str,
            airflow_environment_name: str,
            plugins_version: Optional[str] = None,
            requirements_version: Optional[str] = None,
            **update_environment_kwargs,
            ):
        client = cls.get_client(region)
        _args = {
                **{
                        "Name":                        airflow_environment_name,
                        "PluginsS3ObjectVersion":      plugins_version,
                        "RequirementsS3ObjectVersion": requirements_version,
                        "RequirementsS3Path":          "dags/requirements.txt" if requirements_version else None,
                        },
                **update_environment_kwargs,
                }

        _args = {key: _args[key] for key in _args.keys() if _args[key] is not None}

        client.update_environment(**_args)

        status = client.get_environment(Name=airflow_environment_name)

        while status["Environment"]["Status"] == "UPDATING":
            logging.info("Environment updating...")
            time.sleep(10)
            status = client.get_environment(Name=airflow_environment_name)

        if status["Environment"]["Status"] != "AVAILABLE":
            raise Exception("Airflow is not available after updating environment!")

    @classmethod
    def trigger_airflow_command(cls, token_data, command):
        return requests.post(
                f'https://{token_data["WebServerHostname"]}/aws_mwaa/cli',
                data=command,
                headers={
                        "Content-Type":  "text/plain",
                        "Authorization": f'Bearer {token_data["CliToken"]}',
                        },
                )

    @classmethod
    def setup_k8_config(cls, region: str, airflow_code_bucket: str, infrastructure_environment_name: str):
        eks_cluster_output = cloudformation.get_stack_output(infrastructure_environment_name, "Eks", region)
        eks_cluster_outputs = cloudformation.stack_details(eks_cluster_output, region)
        eks_cluster_name = None
        for output in eks_cluster_outputs["Stacks"][0]["Outputs"]:
            if output["OutputKey"] == "EksClusterName":
                eks_cluster_name = output["OutputValue"]
        if not eks_cluster_name:
            raise Exception("Could not get EKS Cluster infrastructure_environment_name")
        # dirname, filename = os.path.split(os.path.abspath(__file__))
        # kube_config_file = os.path.abspath(f'{dirname}/../dbeng-airflow/mwaa-workspace/dags/kube_config.yaml')
        kube_config_file = f"/tmp/{region}-{infrastructure_environment_name}-kube_config.yaml"
        Path(kube_config_file).touch(0o777)
        command = f"""aws eks update-kubeconfig \
          --region {region} \
          --kubeconfig {kube_config_file} \
          --name {eks_cluster_name} \
          --alias aws"""
        exit_code, status = exe.sub_process_rc(command)
        if exit_code != 0:
            raise Exception(f"Error creating kube_config. [{command}] > [{status}]")
        logging.info(status)

        kube_config_file_hash = hashlib.md5(open(kube_config_file, "rb").read()).hexdigest()

        logging.info(f"Uploading {kube_config_file} to s3://{airflow_code_bucket}/dags/kube_config.yaml")
        kube_config_file_metadata = S3Manager.check_bucket_key(
                region, airflow_code_bucket, "dags/kube_config.yaml", return_metadata=True
                )

        if kube_config_file_metadata and "x-amz-meta-local_hash" in kube_config_file_metadata["ResponseMetadata"]["HTTPHeaders"]:
            remote_hash = kube_config_file_metadata["ResponseMetadata"]["HTTPHeaders"]["x-amz-meta-local_hash"]
            if remote_hash == kube_config_file_hash:
                logging.info("Same file in local and remote. Upload cancelled")
                return

        S3Manager.file_upload(
                region,
                kube_config_file,
                airflow_code_bucket,
                "dags/kube_config.yaml",
                return_response=True,
                extra_args={"Metadata": {"local_hash": kube_config_file_hash}},
                )

    @classmethod
    def get_airflow_status(cls, region: str, airflow_environment_name: str):
        client = cls.get_client(region)

        status = client.get_environment(Name=airflow_environment_name)

        return status["Environment"]["Status"]

    @classmethod
    def get_environment(cls, region: str, airflow_environment_name: str):
        client = cls.get_client(region)

        status = client.get_environment(Name=airflow_environment_name)

        return status

    @classmethod
    def get_airflow_environment_information(cls, region: str, infrastructure_environment_name: str):
        _stack = CloudformationManager.describe_stack(region, infrastructure_environment_name)
        airflow_operational_bucket = None
        airflow_source_code_bucket = None
        airflow_environment_name = None

        _stack_name = _stack["StackName"]
        airflow_arn: str = "//"

        for _o, output in enumerate(_stack["Outputs"]):
            if output["OutputKey"] == "MWAA":
                airflow_arn = output["OutputValue"]
                break

        for _o, output in enumerate(_stack["Parameters"]):
            if output["ParameterKey"] == "MWWAOperationalBucketName":
                airflow_operational_bucket = output["ParameterValue"]
                break

        airflow_arn_parts = airflow_arn.split("/")

        if airflow_arn_parts[1] == "":
            raise Exception("Parse error: Unable to find the environment infrastructure_environment_name")

        airflow_stack_name = airflow_arn_parts[1]
        airflow_stack_details = CloudformationManager.describe_stacks(region, airflow_stack_name)["Stacks"][0]
        airflow_stack_outputs = airflow_stack_details["Outputs"]

        for _o, output in enumerate(airflow_stack_outputs):
            if output["OutputKey"] == "MWWABucketName":
                airflow_source_code_bucket = output["OutputValue"]
            if output["OutputKey"] == "MWAAEnvironmentName":
                airflow_environment_name = output["OutputValue"]

        return {
                "operational_bucket":              airflow_operational_bucket,
                "source_code_bucket":              airflow_source_code_bucket,
                "infrastructure_environment_name": airflow_environment_name,
                "stack_name":                      airflow_stack_name,
                }


class MwaaCodeDeployer:
    AIRFLOW_CODE_REPOSITORY = "git@github.com:RepTrak/dbeng-airflow.git"
    SERVICES_SECRETS_TO_BE_FETCH = ["mongodb", "redis", "mysql", "pgsql"]

    @classmethod
    def sync_dags(
            cls, region: str, airflow_code_bucket: str, destination_folder: str = AIRFLOW_GIT_REPOSITORY_LOCAL_DEST
            ):

        # This is a simple way to get a list of all the files in a directory.
        dags_folder = f"{destination_folder}/mwaa-workspace/dags"
        file_list = []

        for root, dirs, files in os.walk(dags_folder):
            for file in files:
                if file in ["kube_config.yaml", "requirements.txt"]:
                    continue
                # append the file name to the list
                file_list.append(os.path.realpath(os.path.join(root, file)))

        # This code is uploading the DAGs to the S3 bucket.
        dags_sync_keys = []
        for file in file_list:
            file_key = re.sub(r"^.+mwaa-workspace/", "", file)
            file_hash = hashlib.md5(open(file, "rb").read()).hexdigest()
            logging.debug(f"Uploading {file} to s3://{airflow_code_bucket}/{file_key}")
            file_metadata = S3Manager.check_bucket_key(region, airflow_code_bucket, file_key, return_metadata=True)
            if file_metadata and "x-amz-meta-local_hash" in file_metadata["ResponseMetadata"]["HTTPHeaders"]:
                remote_hash = file_metadata["ResponseMetadata"]["HTTPHeaders"]["x-amz-meta-local_hash"]
                if remote_hash == file_hash:
                    dags_sync_keys.append(file_key)
                    logging.debug("Same file in local and remote. Upload cancelled")
                    continue

            S3Manager.file_upload(
                    region,
                    file,
                    airflow_code_bucket,
                    file_key,
                    return_response=True,
                    extra_args={"Metadata": {"local_hash": file_hash}},
                    )
            dags_sync_keys.append(file_key)

        # This code is removing the dags that are not in the dags_sync_keys list.
        objects = S3Manager.list_bucket_objects(region, airflow_code_bucket)
        dags_in_s3 = [file['Key'] for file in objects
                      if file['Key'].startswith('dags/') and
                      file['Key'] not in ['dags/kube_config.yaml', 'dags/requirements.txt']
                      ]

        dags_to_be_removed = list(set(dags_in_s3) - set(dags_sync_keys))

        for dag_to_remove in dags_to_be_removed:
            S3Manager.permanently_delete_object(region, airflow_code_bucket, dag_to_remove)

    @classmethod
    def deploy_requirements(
            cls, region: str, airflow_code_bucket: str, destination_folder: str = AIRFLOW_GIT_REPOSITORY_LOCAL_DEST
            ) -> bool:
        """
        Return bool in case you need to update the airflow instance to get the new version
        """
        # This code is checking if the file has been uploaded to the S3 bucket before. If it has, it will check if the hash of the file is the same as
        # the hash of the file in the bucket. If it is the same, it will cancel the upload.
        requirements_path = os.path.realpath(f"{destination_folder}/mwaa-workspace/dags/requirements.txt")
        file_key = re.sub(r"^.+mwaa-workspace/", "", requirements_path)

        file_hash = hashlib.md5(open(requirements_path, "rb").read()).hexdigest()
        logging.info(f"Uploading {requirements_path} to s3://{airflow_code_bucket}/{file_key}")
        file_metadata = S3Manager.check_bucket_key(region, airflow_code_bucket, file_key, return_metadata=True)
        if file_metadata and "x-amz-meta-local_hash" in file_metadata["ResponseMetadata"]["HTTPHeaders"]:
            remote_hash = file_metadata["ResponseMetadata"]["HTTPHeaders"]["x-amz-meta-local_hash"]
            if remote_hash == file_hash:
                logging.info("Same file in local and remote. Upload cancelled")
                return False

        S3Manager.file_upload(
                region,
                requirements_path,
                airflow_code_bucket,
                file_key,
                return_response=True,
                extra_args={"Metadata": {"local_hash": file_hash}},
                )

        return True

    @classmethod
    def deploy_plugins(
            cls, region: str, airflow_code_bucket: str, destination_folder: str = AIRFLOW_GIT_REPOSITORY_LOCAL_DEST
            ) -> bool:
        """
        Return bool in case you need to update the airflow instance to get the new version
        """

        plugins_folder_path = os.path.realpath(f"{destination_folder}/mwaa-workspace/plugins")
        plugins_zip_path = os.path.realpath(f"{destination_folder}/mwaa-workspace/plugins.zip")
        logging.info("Creating plugins.zip")
        shutil.make_archive(plugins_folder_path, "zip", plugins_folder_path)
        file_key = re.sub(r"^.+mwaa-workspace/", "", plugins_zip_path)

        file_hash = hashlib.md5(open(plugins_zip_path, "rb").read()).hexdigest()
        logging.info(f"Uploading {plugins_zip_path} to s3://{airflow_code_bucket}/{file_key}")
        file_metadata = S3Manager.check_bucket_key(region, airflow_code_bucket, file_key, return_metadata=True)
        if file_metadata and "x-amz-meta-local_hash" in file_metadata["ResponseMetadata"]["HTTPHeaders"]:
            remote_hash = file_metadata["ResponseMetadata"]["HTTPHeaders"]["x-amz-meta-local_hash"]
            if remote_hash == file_hash:
                logging.info("Same file in local and remote. Upload cancelled")
                return False

        S3Manager.file_upload(
                region,
                plugins_zip_path,
                airflow_code_bucket,
                file_key,
                return_response=True,
                extra_args={"Metadata": {"local_hash": file_hash}},
                )

        return True

    @classmethod
    def clone_repository(
            cls, branch: str = "develop", destination_folder: str = AIRFLOW_GIT_REPOSITORY_LOCAL_DEST, cleanup: bool = True
            ):
        destination_folder = os.path.realpath(destination_folder)
        logging.info(f"Cloning {branch} is {destination_folder}")
        if cleanup:
            logging.info(f"Cleaning directory {destination_folder}")
            if os.path.isdir(destination_folder):
                shutil.rmtree(destination_folder)
        try:
            repo = Repo.clone_from(cls.AIRFLOW_CODE_REPOSITORY, destination_folder)
        except GitCommandError as e:
            logging.error(f"{e.command} > {e.stdout}")
            logging.info(f"Setting repository from local dir {destination_folder}")
            repo = Repo(destination_folder)

        logging.info(f"Fetching branch {branch}")
        repo.git.fetch()
        logging.info(f"Checking out branch {branch}")
        repo.git.checkout(branch)

        logging.info(f"Pulling latest changes in branch {branch}")
        repo.git.pull()

    @classmethod
    def import_remote_variables_reference(
            cls,
            region: str,
            airflow_stack_name: str,
            airflow_environment_name: str,
            airflow_operational_bucket: str,
            infrastructure_env_name: str,
            ):
        remote_variables = SecretManager.get_secrets(
                region, filters=[{"Key": "name", "Values": [f"airflow/{airflow_stack_name}/variable"]}]
                )

        remote_variables_keys = cls.get_custom_backend_resource_keys(remote_variables)

        remote_connections = SecretManager.get_secrets(
                region, [{"Key": "name", "Values": [f"airflow/{airflow_stack_name}/connection"]}]
                )

        remote_connection_keys = cls.get_custom_backend_resource_keys(remote_connections)

        references_variables = {
                "airflow-main-region":                    region,
                "infrastructure-env-name":                infrastructure_env_name,
                "airflow-stack-name":                     airflow_stack_name,
                "operational-bucket":                     airflow_operational_bucket,
                "airflow-custom-backend-variable-keys":   remote_variables_keys,
                "airflow-custom-backend-connection-keys": remote_connection_keys,
                }

        cli_token_response = MwaaManager.create_cli_token(region, airflow_environment_name)
        for key in references_variables.keys():
            r = MwaaManager.trigger_airflow_command(
                    cli_token_response, f"variables set {key} {references_variables[key]}"
                    )
            logging.debug(f'Set variable "{key}" with HTTP status: [{r.status_code}]')

    @classmethod
    def get_custom_backend_resource_keys(cls, remote_connections):
        remote_connection_keys = []
        for page in remote_connections["SecretList"]:
            for remote_conn in page["SecretList"]:
                remote_conn_name_parts = remote_conn["Name"].split("/")
                remote_conn_name_parts.reverse()
                remote_connection_keys.append(remote_conn_name_parts[0])
        remote_connection_keys = json.dumps(remote_connection_keys).strip('"')
        remote_connection_keys = f"'{remote_connection_keys}'"
        return remote_connection_keys

    @classmethod
    def import_services_secrets_as_variables(
            cls,
            region: str,
            master_region: str,
            airflow_stack_name: str,
            infrastructure_env_name: str,
            prefix_region: bool = False,
            ):
        service_secrets = {}
        for service in cls.SERVICES_SECRETS_TO_BE_FETCH:
            try:
                service_secrets[service] = ServiceSecretManager.fetch_infra_service_secret(
                        service, infrastructure_env_name, region
                        )
            except Exception as e:
                logging.error(
                        f"Could not get secrets for service {service} in region {region} in env {infrastructure_env_name}. [{e}]"
                        )

        if prefix_region:
            service_secrets = {
                    f'{key.upper()}.{region.replace("-", "_").upper()}': json.dumps(service_secrets[key])
                    for key in service_secrets.keys()
                    }

        for key in service_secrets.keys():
            SecretManager.create_secret(
                    master_region,
                    f"airflow/{airflow_stack_name}/variable/{key}",
                    service_secrets[key],
                    secret_desc="Airflow secret",
                    )

        registries = EcrManager.get_registries('us-east-1')
        registry_url = registries[0]["repositoryUri"].split("/")[0]
        airflow_stack_name = MwaaManager.get_airflow_environment_information(region, infrastructure_env_name)[
            "stack_name"
        ]

        SecretManager.create_secret(
                master_region,
                f"airflow/{airflow_stack_name}/variable/ECR_HOST",
                registry_url,
                secret_desc="ECR Host variable for airflow",
                )

        SecretManager.create_secret(
                master_region,
                f"airflow/{airflow_stack_name}/variable/master_region",
                master_region,
                secret_desc="Airflow secret",
                )

    @classmethod
    def import_local_variables(
            cls,
            region,
            airflow_environment_name: str,
            infrastructure_environment_name: str,
            kms_key: str,
            repository_local_folder: str = AIRFLOW_GIT_REPOSITORY_LOCAL_DEST,
            ):
        client = MwaaManager.get_client(region)

        decrypted_content = EncryptionManager.decrypt_file(
                f"{repository_local_folder}/secrets_encrypted/{infrastructure_environment_name}.json", [kms_key]
                )
        variables_file_data = json.loads(decrypted_content)

        for variable_key in variables_file_data.keys():
            cli_token_response = client.create_cli_token(Name=airflow_environment_name)
            variable_value = variables_file_data[variable_key]

            if type(variable_value) in [dict, list]:
                variable_value = json.dumps(variable_value).strip('"')
                variable_value = f"'{variable_value}'"

            if variable_value == "":
                variable_value = None

            # cli_token_response = client.create_cli_token(Name = airflow_environment_name)
            airflow_command = f"variables set {variable_key} {variable_value}"
            r = MwaaManager.trigger_airflow_command(cli_token_response, airflow_command)
            logging.debug(f'Set variable "{variable_key}" with HTTP status: [{r.status_code}]')
            if r.status_code != 200:
                log = f'Error setting variable "{variable_key}". {r.status_code}:{r.text}'
                logging.error(log)
                raise Exception(log)


class MwaaAwsInfrastructureServiceDeployer(AwsInfrastructureServiceDeployer):
    __bucket_name: str
    __bucket_name_op: str

    def __init__(self, environment_name: str, region: str, environment: Dict[str, str]):
        super().__init__(environment_name, region, environment)
        self.__bucket_name = f"mwaa-{environment_name}-{region}"
        self.__bucket_name_op = f"mwaa-op-{environment_name}-{region}"

    def build_params(self, cloudformation_parameters: Optional[List[Dict[str, str]]] = []):
        cloudformation_parameters.append({"ParameterKey": "MWWABucketName", "ParameterValue": self.__bucket_name})
        cloudformation_parameters.append(
                {"ParameterKey": "MWWAOperationalBucketName", "ParameterValue": self.__bucket_name_op}
                )

        return cloudformation_parameters

    def build_params_for_stack(self, stack_name: str, cloudformation_parameters: Optional[List[Dict[str, str]]] = []):
        return self.build_params(cloudformation_parameters=cloudformation_parameters)

    def post_delete(self):
        S3Manager.delete_bucket(self.region, self.__bucket_name)
        S3Manager.delete_bucket(self.region, self.__bucket_name_op)

    def pre_build(self):
        try:
            S3Manager.create_bucket(self.region, self.__bucket_name, versioning=True)
        except Exception as e:
            logging.error(e)
            pass
        finally:
            S3Manager.create_folder(self.region, self.__bucket_name, "dags")

            requirements_txt_exists = S3Manager.check_bucket_key(
                    self.region, self.__bucket_name, "dags/requirements.txt"
                    )

            if not requirements_txt_exists:
                temporal_file = "/tmp/mwaa_empty_requirements.txt"
                if not os.path.isfile(temporal_file):
                    with open(temporal_file, "wb") as fp:
                        pass
                S3Manager.file_upload(self.region, temporal_file, self.__bucket_name, "dags/requirements.txt")

            plugins_zip_exists = S3Manager.check_bucket_key(self.region, self.__bucket_name, "plugins.zip")

            if not plugins_zip_exists:
                temporal_file = "/tmp/mwaa_empty_plugins.zip"
                if not os.path.isfile(temporal_file):
                    with ZipFile(temporal_file, "w") as file:
                        pass
                S3Manager.file_upload(self.region, temporal_file, self.__bucket_name, "plugins.zip")

            try:
                S3Manager.create_bucket(self.region, self.__bucket_name_op)
            except Exception:
                pass
            finally:
                if not S3Manager.check_bucket_key(self.region, self.__bucket_name_op, "dbeng"):
                    S3Manager.create_folder(self.region, self.__bucket_name_op, "dbeng")
                if not S3Manager.check_bucket_key(self.region, self.__bucket_name_op, "media"):
                    S3Manager.create_folder(self.region, self.__bucket_name_op, "media")
                if not S3Manager.check_bucket_key(self.region, self.__bucket_name_op, "data-science"):
                    S3Manager.create_folder(self.region, self.__bucket_name_op, "data-science")

        self.deployed = True

    def pre_delete(self):
        airflow_stack_info = MwaaManager.get_airflow_environment_information(self.region, self.environment_name)
        airflow_stack_name = airflow_stack_info["stack_name"]
        remote_variables = SecretManager.get_secrets(
                self.region, filters=[{"Key": "name", "Values": [f"airflow/{airflow_stack_name}/variable"]}]
                )
        self.__delete_secrets(remote_variables)

        remote_variables = SecretManager.get_secrets(
                self.region, filters=[{"Key": "name", "Values": [f"airflow/{airflow_stack_name}/connection"]}]
                )
        self.__delete_secrets(remote_variables)

    def __delete_secrets(self, remote_variables):
        for page in remote_variables["SecretList"]:
            for remote_conn in page["SecretList"]:
                remote_conn_name = remote_conn["Name"]
                SecretManager.delete_secret(self.region, remote_conn_name, raise_on_error=False)

    def post_build(self):
        region = self.environment["Region"]
        registries = EcrManager.get_registries(region)
        registry_url = registries[0]["repositoryUri"].split("/")[0]
        airflow_stack_name = MwaaManager.get_airflow_environment_information(region, self.environment["Name"])[
            "stack_name"
        ]
        SecretManager.create_secret(
                region,
                f"airflow/{airflow_stack_name}/variable/ECR_HOST",
                registry_url,
                secret_desc="ECR Host variable for airflow",
                )

    def pre_update(self):
        self.pre_build()

    def post_update(self):
        region = self.environment["Region"]
        registries = EcrManager.get_registries(region)
        registry_url = registries[0]["repositoryUri"].split("/")[0]
        airflow_stack_name = MwaaManager.get_airflow_environment_information(region, self.environment["Name"])[
            "stack_name"
        ]
        SecretManager.update_secret(
                region,
                f"airflow/{airflow_stack_name}/variable/ECR_HOST",
                registry_url,
                secret_desc="ECR Host variable for airflow",
                )
