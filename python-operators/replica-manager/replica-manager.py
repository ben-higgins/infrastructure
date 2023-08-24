import argparse
import time
import os
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# expects an environment variable "ENVTYPE"
namespace = "default"

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


# set pod scale number
if os.environ["ENVTYPE"] == "main":
    core_api = client.CoreV1Api()
    response = core_api.list_node()
    node_count = len(response.items)
else:
    # set everything else to a single pod
    node_count = 1

eks_api = client.AppsV1Api()

while True:

    response = eks_api.list_namespaced_deployment(namespace=namespace, label_selector='owner=eng')
    print(response)

    for i in response.items:
        print(f'{i.metadata.name} replicas: {i.spec.replicas}')

        # change replica number
        if os.environ["ENVTYPE"] == "main" and i.spec.replicas < 3:
            api_response = eks_api.patch_namespaced_deployment_scale(
                i.metadata.name,
                namespace,
                {'spec': {'replicas': 3}}
            )
            print(f'Scaled up {i.metadata.name} to {3}')
        elif i.spec.replicas != node_count:
            api_response = eks_api.patch_namespaced_deployment_scale(
                i.metadata.name,
                namespace,
                {'spec': {'replicas': node_count}}
            )
            print(f'Scaled down {i.metadata.name} to {node_count}')

    time.sleep(60)

