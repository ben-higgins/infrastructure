import hashlib
import warnings
from datetime import datetime
from time import sleep
from typing import Dict, List, Optional

import boto3
import sqlalchemy as sa

from .cloudformation_manager import CloudformationManager
from .core_components import AwsInfrastructureServiceDeployer, AwsServiceManager
from .logger import logging

QUERIES = {
    "get_users_and_groups": """SELECT usename as username, groname as groupname
FROM pg_user, pg_group
WHERE pg_user.usesysid = ANY(pg_group.grolist)
AND pg_group.groname in (SELECT DISTINCT pg_group.groname from pg_group)""",
    "create_user": "create user {user} with password '{passwd}'",
    "alter_user": "alter user {user} password '{passwd}'",
    "add_user_to_group": "alter group {group} add user {user}",
}


def fetch_cluster_description(redshift_env, region):
    warnings.warn(
        f"fetch_cluster_description is deprecated, use {RedshiftManager.__module__}.RedshiftManager.fetch_cluster_description instead",
        DeprecationWarning,
    )
    RedshiftManager.fetch_cluster_description(region, redshift_env)


def create_snapshot(redshift_env, src_region, dst_region):
    warnings.warn(
        f"create_snapshot is deprecated, use {RedshiftManager.__module__}.RedshiftManager.create_snapshot_between_regions instead",
        DeprecationWarning,
    )
    RedshiftManager.create_snapshot_between_regions(redshift_env, src_region, dst_region)


def fetch_latest_snapshot(redshift_env, src_region, dst_region):
    warnings.warn(
        f"fetch_latest_snapshot is deprecated, use {RedshiftManager.__module__}.RedshiftManager.fetch_latest_snapshot_between_regions instead",
        DeprecationWarning,
    )

    return RedshiftManager.fetch_latest_snapshot_between_regions(redshift_env, src_region, dst_region)


def set_cluster_master_password(cluster_id, region, password):
    warnings.warn(
        f"set_cluster_master_password is deprecated, use {RedshiftManager.__module__}.RedshiftManager.set_cluster_master_password instead",
        DeprecationWarning,
    )
    return RedshiftManager.set_cluster_master_password(region, cluster_id, password)


def get_database_client(user, passwd, host):
    warnings.warn(
        f"get_database_client is deprecated, use {RedshiftManager.__module__}.RedshiftManager.get_db_connection instead",
        DeprecationWarning,
    )
    return RedshiftManager.get_db_connection(user, passwd, host, "dev")


class RedshiftManager(AwsServiceManager):
    service = "redshift"
    __db_connections = {}

    @classmethod
    def get_db_connection(
        cls, user: str, passwd: str, host: str, db_name: str, protocol: str = "redshift+psycopg2"
    ) -> boto3.session.Session.client:
        connection_string = f"{protocol}://{user}:{passwd}@{host}/{db_name}"
        db_key = hashlib.md5(connection_string.encode())

        if db_key not in cls.__db_connections:
            cls.__db_connections[db_key] = sa.create_engine(connection_string)
        return cls.__db_connections[db_key]

    @classmethod
    def fetch_cluster_description(cls, region: str, redshift_env: str):
        client = cls.get_client(region)

        cluster = client.describe_clusters(
            MaxRecords=20,
            TagKeys=[
                "Environment",
            ],
            TagValues=[
                redshift_env,
            ],
        )
        return cluster

    @classmethod
    def set_cluster_master_password(cls, region, cluster_id, password):
        client = cls.get_client(region)
        status = client.describe_clusters(ClusterIdentifier=cluster_id)

        if "MasterUserPassword" in status["Clusters"][0]["PendingModifiedValues"].keys():
            logging.info("MasterUserPassword operation in progress")
            return

        client.modify_cluster(
            ClusterIdentifier=cluster_id,
            MasterUserPassword=password,
        )

        sleep(1)

        status = client.describe_clusters(ClusterIdentifier=cluster_id)
        while "MasterUserPassword" in status["Clusters"][0]["PendingModifiedValues"].keys():
            logging.info("MasterUserPassword operation in progress... this action will take a while")
            sleep(30)
            status = client.describe_clusters(ClusterIdentifier=cluster_id)

    @classmethod
    def fetch_latest_snapshot_between_regions(cls, redshift_env_name, src_region, dst_region):
        client = cls.get_client(dst_region)
        print(f'Destination region: {dst_region}')
        print(f'Source region: {src_region}')
        print(f'Redshift environment: {redshift_env_name}')
        redshift_cluster_id = cls.fetch_cluster_description(src_region, redshift_env_name)
        print(f'Redshift cluster id: {redshift_cluster_id["Clusters"][0]["ClusterIdentifier"]}')
        all_snapshots = client.describe_cluster_snapshots(
            ClusterIdentifier=redshift_cluster_id["Clusters"][0]["ClusterIdentifier"],
            MaxRecords=20,
            SortingEntities=[
                {"Attribute": "CREATE_TIME", "SortOrder": "DESC"},
            ],
        )

        latest_snapshot = all_snapshots["Snapshots"][0]["SnapshotIdentifier"]

        return latest_snapshot

    @classmethod
    def create_snapshot_between_regions(cls, redshift_env_name: str, src_region: str, dst_region: str):
        client = cls.get_client(src_region)

        redshift_cluster_id = cls.fetch_cluster_description(src_region, redshift_env_name)["Clusters"][0][
            "ClusterIdentifier"
        ]
        current_date_time = datetime.today().strftime("%Y-%m-%d-%H-%M-%S")

        snapshot = client.create_cluster_snapshot(
            SnapshotIdentifier=redshift_cluster_id + "-" + current_date_time,
            ClusterIdentifier=redshift_cluster_id,
            ManualSnapshotRetentionPeriod=30,
            Tags=[
                {"Key": "RedshiftClusterID", "Value": redshift_cluster_id},
                {"Key": "Environment", "Value": redshift_env_name},
            ],
        )

        snapshot_id = snapshot["Snapshot"]["SnapshotIdentifier"]
        snapshot_status = client.describe_cluster_snapshots(SnapshotIdentifier=snapshot_id)["Snapshots"][0]["Status"]

        logging.info("Creating redshift snapshot " + str(snapshot_id) + " in " + str(src_region) + " region")
        while snapshot_status != "available":
            logging.info(f"Waiting for finish snapshot. Status: {snapshot_status}")
            sleep(10)
            snapshot_status = client.describe_cluster_snapshots(SnapshotIdentifier=snapshot_id)["Snapshots"][0][
                "Status"
            ]

        snapshot_status = client.describe_cluster_snapshots(SnapshotIdentifier=snapshot_id)["Snapshots"][0]["Status"]
        if snapshot_status == "available":
            logging.info(
                "Redshift snapshot " + str(snapshot_id) + " is available for use in " + str(src_region) + " region"
            )

        if src_region != dst_region:
            dst_snapshot_id = "copy:" + snapshot_id
            latest_snapshot = cls.fetch_latest_snapshot_between_regions(redshift_env_name, src_region, dst_region)

            logging.info(
                "Waiting for redshift snapshot "
                + str(dst_snapshot_id)
                + " to become available in "
                + str(dst_region)
                + " region"
            )
            while latest_snapshot != dst_snapshot_id:
                logging.info(f"Waiting destination snapshot alignment with latest snapshot. Status: {latest_snapshot}")
                sleep(10)
                latest_snapshot = cls.fetch_latest_snapshot_between_regions(redshift_env_name, src_region, dst_region)

            dst_rs_client = cls.get_client(dst_region)
            dst_snapshot_status = dst_rs_client.describe_cluster_snapshots(SnapshotIdentifier=dst_snapshot_id)[
                "Snapshots"
            ][0]["Status"]

            while dst_snapshot_status != "available":
                logging.info(f"Waiting snapshot in destination Status: {dst_snapshot_status}")
                sleep(10)
                dst_snapshot_status = dst_rs_client.describe_cluster_snapshots(SnapshotIdentifier=dst_snapshot_id)[
                    "Snapshots"
                ][0]["Status"]

            dst_snapshot_status = dst_rs_client.describe_cluster_snapshots(SnapshotIdentifier=dst_snapshot_id)[
                "Snapshots"
            ][0]["Status"]
            if dst_snapshot_status == "available":
                logging.info(
                    "Redshift snapshot "
                    + str(dst_snapshot_id)
                    + " is available for use in "
                    + str(dst_region)
                    + " region"
                )

    @classmethod
    def get_latest_snapshot_id_from_build_environment(cls, environment):
        _env = environment["EnvType"]
        _snapshot_src_region = environment["RedshiftSrcClusterRegion"]
        _snapshot_dst_region = environment["Region"]
        if _env not in ["develop", "prod"]:
            _env = "develop"
        if _snapshot_dst_region not in ["eu-west-1", "eu-central-1"]:
            _snapshot_dst_region = "eu-west-1"

        if "RedshiftCreateLatestSnapshot" in environment and environment["RedshiftCreateLatestSnapshot"] == "true":
            cls.create_snapshot_between_regions(_env, _snapshot_src_region, _snapshot_dst_region)
            return cls.fetch_latest_snapshot_between_regions(_env, _snapshot_src_region, _snapshot_dst_region)
        elif "RedshiftRestoreSpecificSnapshot" in environment:
            return environment["RedshiftRestoreSpecificSnapshot"]

        return cls.fetch_latest_snapshot_between_regions(_env, _snapshot_src_region, _snapshot_dst_region)


class RedshiftAwsInfrastructureServiceDeployer(AwsInfrastructureServiceDeployer):
    def build_params(self, cloudformation_parameters: Optional[List[Dict[str, str]]] = []):
        cloudformation_parameters.append(
            {
                "ParameterKey": "RedshiftSnapshotId",
                "ParameterValue": RedshiftManager.get_latest_snapshot_id_from_build_environment(self.environment),
            }
        )
        return cloudformation_parameters

    def build_params_for_stack(self, stack_name: str, cloudformation_parameters: Optional[List[Dict[str, str]]] = []):
        _stack = CloudformationManager.describe_stack(self.region, self.environment_name)
        _stack_name = _stack["StackName"]
        _redshift_arn: str = "//"

        for _o, output in enumerate(_stack["Outputs"]):
            if output["OutputKey"] == "Redshift":
                _redshift_arn = output["OutputValue"]

        _redshift_arn_parts = _redshift_arn.split("/")

        # If redshift ARN doesn't seems valid, raise an exception
        if len(_redshift_arn_parts) != 3 and _redshift_arn_parts[1] == "":
            raise Exception(f"{_redshift_arn} is not a valid arn")
        # If redshift isn't deployed already so get the lastest redshift snapshot ID that can be used to deploy redshift
        elif len(_redshift_arn_parts) == 3 and _redshift_arn_parts[1] == "":
            cloudformation_parameters.append(
                {
                    "ParameterKey": "RedshiftSnapshotId",
                    "ParameterValue": RedshiftManager.get_latest_snapshot_id_from_build_environment(self.environment),
                }
            )

        # If redshift is already deployed, fetch the already used redshift snapshot ID so that redshift data must not be replaced
        elif len(_redshift_arn_parts) == 3 and _redshift_arn_parts[1] != "":
            _redshift_stack_name = _redshift_arn_parts[1]
            _redshift_stack_details = CloudformationManager.describe_stack(self.region, _redshift_stack_name)
            for _o, output in enumerate(_redshift_stack_details["Parameters"]):
                if output["ParameterKey"] == "SnapshotIdentifier":
                    cloudformation_parameters.append(
                        {"ParameterKey": "RedshiftSnapshotId", "ParameterValue": output["ParameterValue"]}
                    )
                    break

        return cloudformation_parameters

    def pre_delete(self):
        pass

    def post_delete(self):
        pass

    def pre_build(self):
        pass

    def post_build(self):
        pass

    def pre_update(self):
        pass

    def post_update(self):
        pass
