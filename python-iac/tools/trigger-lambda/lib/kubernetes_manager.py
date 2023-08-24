import os
import time

import boto3
import lib.exec_ctl as exe
from kubernetes import client, config, dynamic
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
from kubernetes.client import api_client

from .cloudformation_manager import CloudformationManager


class KubernetesManager:
    def __init__(self, cluster_name, region):
        boto_client = boto3.client("cloudformation", region_name=region)

        response = boto_client.describe_stacks(StackName=cluster_name)
        outputs = response["Stacks"][0]["Outputs"]
        for output in outputs:
            if output["OutputKey"] == "EKSConfig":
                print(f"Updating local kube config file: {output['OutputValue']}", flush=True)
                command = output["OutputValue"]
                exe.sub_process(command.split())
                time.sleep(10)

        config.load_kube_config(config_file=os.getenv("KUBECONFIG"))
        self.__client = client.CoreV1Api()

    @staticmethod
    def get_cluster(branchName, region):
        client = boto3.client("cloudformation", region_name=region)

        response = client.list_stacks(
            StackStatusFilter=[
                "CREATE_COMPLETE",
                "ROLLBACK_FAILED",
                "ROLLBACK_COMPLETE",
                "UPDATE_COMPLETE",
                "UPDATE_ROLLBACK_COMPLETE",
            ]
        )

        if len(response["StackSummaries"]) == 0:
            print(f"No cloudformation stack found in {region} region", flush=True)
            return

        for key in response["StackSummaries"]:
            if branchName + "-Eks" in key["StackName"]:
                clusterName = key["StackName"]
                print(f"EKS cluster name: {clusterName}", flush=True)
                return clusterName

    def get_pods(self):
        response = self.__client.list_pod_for_all_namespaces(watch=False)
        return [(pod.metadata.name, pod.metadata.namespace, pod.status.phase) for pod in response.items]

    def execute_command(self, pod_name, namespace, command, stderr=True, stdin=False, stdout=True, tty=False):
        try:
            api_response = stream(
                self.__client.connect_get_namespaced_pod_exec,
                pod_name,
                namespace,
                command=command,
                stderr=stderr,
                stdin=stdin,
                stdout=stdout,
                tty=tty,
                _preload_content=True,
            )
            return api_response
        except ApiException as e:
            print(f"Exception when calling CoreV1Api->connect_post_namespaced_pod_exec: {e}\n {e.reason}", flush=True)

    @classmethod
    def update_kubeconfig(cls, stack_name: str, region: str):
        outputs = CloudformationManager.get_stack_outputs(region, stack_name)
        for output in outputs:
            if output["OutputKey"] == "EKSConfig":
                print("updating local kube config file: " + output["OutputValue"])
                command = output["OutputValue"]
                o = exe.sub_process(command)
                print(f"cmd output: {o}")

    @staticmethod
    def get_service_url(service_name: str):
        # https://github.com/kubernetes-client/python/blob/master/examples/dynamic-client/service.py
        client = dynamic.DynamicClient(
            api_client.ApiClient(configuration=config.load_kube_config())
        )

        # fetching the service api
        api = client.resources.get(api_version="v1", kind="Service")

        # Listing service `frontend-service` in the `default` namespace
        service_created = api.get(name=service_name, namespace="default")
        return service_created.status.loadBalancer.ingress[0].hostname
