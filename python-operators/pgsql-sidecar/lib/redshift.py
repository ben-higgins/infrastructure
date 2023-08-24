#!/usr/bin/python

import boto3

def fetch_cluster_description(redshift_env, region):
    client = boto3.client('redshift', region_name=region)
    cluster = client.describe_clusters(
        MaxRecords=20,
        TagKeys=[
            'Environment',
        ],
        TagValues=[
            redshift_env,
        ],
    )
    return cluster


def fetch_latest_snapshot(redshift_env, region):
    client = boto3.client('redshift', region_name=region)

    # If the production region changes, it will break
    redshift_cluster_id = fetch_cluster_description(redshift_env, 'eu-central-1')

    all_snapshots = client.describe_cluster_snapshots(
        ClusterIdentifier=redshift_cluster_id['Clusters'][0]['ClusterIdentifier'],
        MaxRecords=20,
        SortingEntities=[
            {
                'Attribute': 'CREATE_TIME',
                'SortOrder': 'DESC'
            },
        ]
    )

    latest_snapshot = all_snapshots['Snapshots'][0]['SnapshotIdentifier']

    return latest_snapshot
