import boto3
import argparse
from pprint import pprint
from lib.infrastructure_build_manager import InfrastructureBuildManager

parser = argparse.ArgumentParser()
parser.add_argument("--envName", required=True, help="environment name")
args = parser.parse_args()

environment = args.envName
backupsToKeep = 3


def delete_rds_instance_snapshots(region, snapshotsList, environment, backupsToKeep):
    rds = boto3.client('rds', region_name=region)

    # Extract the names of rdstypes from the list of snapshots of an environment
    rdsTypes = []
    for snapshot in snapshotsList:
        if environment in snapshot['DBInstanceIdentifier']:
            rdsTypes += snapshot['DBSnapshotIdentifier'].split('-')[1:2]

    # Loop throught the distinctive names of rdstypes
    for rdsType in set(rdsTypes):
        snapshotsDict = {}
        rdsIndentifier = f"{environment}-{rdsType}"

        # Make a list of Snapshot name along with Snapshot creation time
        for snapshot in snapshotsList:
            if rdsIndentifier in snapshot['DBInstanceIdentifier']:
                snapshotsDict[snapshot['DBSnapshotIdentifier']] = snapshot['OriginalSnapshotCreateTime']

        # Sort the list of snapshots, newest backups on top
        # https://stackoverflow.com/a/2258273
        sortedSnapshots = sorted(snapshotsDict.items(), key=lambda item: item[1], reverse=True)
        numOfSnapshotsToRemove = len(sortedSnapshots[backupsToKeep:])

        if numOfSnapshotsToRemove > 0:
            print(f"\nRemoving {rdsIndentifier} db instance snapshots")

            for item in sortedSnapshots[backupsToKeep:]:
                # DEBUGGING
                # print(item[1],item[0])

                dbSnapshot = item[0]
                try:
                    rds.delete_db_snapshot(
                        DBSnapshotIdentifier=dbSnapshot,
                    )
                    print(f"RDS snapshot {dbSnapshot} has been deleted")
                except Exception as e:
                    print(f"Unable to delete snapshot {dbSnapshot}\n {e}")

        else:
            print(f"\n{rdsIndentifier} db instance has {len(sortedSnapshots)} snapshots only, so nothing to remove here")

def delete_rds_cluster_snapshots(region, snapshotsList, environment, backupsToKeep):
    rds = boto3.client('rds', region_name=region)

    # Extract the names of rdstypes from the list of snapshots of an environment
    rdsTypes = []
    for snapshot in snapshotsList:
        if environment in snapshot['DBClusterIdentifier']:
            rdsTypes += snapshot['DBClusterSnapshotIdentifier'].split('-')[1:2]

    # Loop throught the distinctive names of rdstypes
    for rdsType in set(rdsTypes):
        snapshotsDict = {}
        rdsIndentifier = f"{environment}-{rdsType}"

        # Make a list of Snapshot name along with Snapshot creation time
        for snapshot in snapshotsList:
            if rdsIndentifier in snapshot['DBClusterIdentifier']:
                snapshotsDict[snapshot['DBClusterSnapshotIdentifier']] = snapshot['SnapshotCreateTime']

        # Sort the list of snapshots, newest backups on top
        # https://stackoverflow.com/a/2258273
        sortedSnapshots = sorted(snapshotsDict.items(), key=lambda item: item[1], reverse=True)
        numOfSnapshotsToRemove = len(sortedSnapshots[backupsToKeep:])

        if numOfSnapshotsToRemove > 0:
            print(f"\nRemoving {rdsIndentifier} db cluster snapshots")

            for item in sortedSnapshots[backupsToKeep:]:
                # DEBUGGING
                # print(item[1],item[0])

                dbSnapshot = item[0]
                try:
                    rds.delete_db_cluster_snapshot(
                        DBClusterSnapshotIdentifier=dbSnapshot,
                    )
                    print(f"RDS snapshot {dbSnapshot} has been deleted")
                except Exception as e:
                    print(f"Unable to delete snapshot {dbSnapshot}\n {e}")

        else:
            print(f"\n{rdsIndentifier} db cluster has {len(sortedSnapshots)} snapshots only, so nothing to remove here")


def list_rds_snapshots(region, environment, backupsToKeep):
    rds = boto3.client('rds', region_name=region)

    instanceResponse = rds.describe_db_snapshots(
        SnapshotType='manual',
        Filters=[
            {
                'Name': 'engine',
                'Values': [
                    'mysql',
                    'postgres'
                ]
            },
        ],
    )
    if 'DBSnapshots' in instanceResponse:

        instanceSnapshotFound = False
        for snapshot in instanceResponse['DBSnapshots']:
            if environment in snapshot['DBSnapshotIdentifier']:
                instanceSnapshotFound = True
                break

        if instanceSnapshotFound:
            delete_rds_instance_snapshots(region, instanceResponse['DBSnapshots'], environment, backupsToKeep)
        else:
            print(f"\nNo RDS Instance Snapshots found for {environment} environment")
    else:
        print(f"\nNo RDS Instance Snapshots found")


    clusterResponse = rds.describe_db_cluster_snapshots(
        SnapshotType='manual',
        Filters=[
            {
                'Name': 'engine',
                'Values': [
                    'aurora',
                ]
            },
        ],
    )
    if 'DBClusterSnapshots' in clusterResponse:

        clusterSnapshotFound = False
        for snapshot in clusterResponse['DBClusterSnapshots']:
            if environment in snapshot['DBClusterSnapshotIdentifier']:
                clusterSnapshotFound = True
                break

        if clusterSnapshotFound:
            delete_rds_cluster_snapshots(region, clusterResponse['DBClusterSnapshots'], environment, backupsToKeep)
        else:
            print(f"\nNo RDS Cluster Snapshots found for {environment} environment")
    else:
        print(f"\nNo RDS Cluster Snapshots found")


def list_redshift_snapshots(region, environment, backupsToKeep):
    redshift = boto3.client('redshift', region_name=region)

    clusterResponse = redshift.describe_cluster_snapshots(
        SnapshotType='manual',
    )
    pprint(clusterResponse)

    if 'Snapshots' in clusterResponse:
        # DEBUGGING
        # pprint(clusterResponse)

        clusterSnapshotFound = False
        for snapshot in clusterResponse['Snapshots']:
            if environment in snapshot['SnapshotIdentifier']:
                clusterSnapshotFound = True
                break

        if clusterSnapshotFound:
            delete_rds_cluster_snapshots(region, clusterResponse['Snapshots'], environment, backupsToKeep)
        else:
            print(f"\nNo Redshift Cluster Snapshots found for {environment} environment")
    else:
        print(f"\nNo Redshift Cluster Snapshots found")



# Create a list of all regions of the env
paramsDir = "./params/" + environment + "/"

regions_sorted_list = InfrastructureBuildManager.prepare_region_builds(paramsDir, environment)

# Loop through the list of regions and perform the selected action on every region
for region in regions_sorted_list:
    regionName = region["RegionName"]

    print(f"Cleaning RDS snapshots of {environment} environment")
    list_rds_snapshots(regionName, environment, backupsToKeep)

    # Redshift cluster names doesn't have identification of env
    # print(f"Cleaning Redshift snapshots of {environment} environment")
    # list_redshift_snapshots(regionName, environment, backupsToKeep)
