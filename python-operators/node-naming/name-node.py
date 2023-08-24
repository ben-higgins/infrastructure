import requests
import boto3
import time
import os
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# connect to cluster
try:
    ## https://github.com/kubernetes-client/python/blob/master/examples/in_cluster_config.py
    config.load_incluster_config()
except config.ConfigException:
    print("Failed to load_incluster_config. Trying to load_kube_config")
    try:
        config.load_kube_config()
    except config.ConfigException:
        raise Exception("Could not configure kubernetes python client")
        exit(1)


core_api = client.CoreV1Api()
response = core_api.list_node()

#for i in response.items:
keys = response.items[0].metadata.labels
for k,v in keys.items():
    if k == "clusterName":
        clusterName = v
    if k == "topology.kubernetes.io/region":
        region = v


client = boto3.client('ec2', region_name=region)
filters = [{'Name':'tag:eks:cluster-name', 'Values':[clusterName]}]

ec2 = boto3.resource('ec2', region_name=region)

while True:
    instances = client.describe_instances(Filters=filters)

    for k, v in instances.items():
        if k == "Reservations":
            for g in v:
                for i, vals in g.items():
                    if i == "Instances":
                        for n in vals:
                            print(n["InstanceId"])
                            try:
                                ec2.create_tags(Resources=[n["InstanceId"]],
                                                Tags=[{'Key': 'Name', 'Value': f'{clusterName}-node'}])
                            except:
                                print(f'Failed to tag instance {n["InstanceId"]}')
    time.sleep(60)