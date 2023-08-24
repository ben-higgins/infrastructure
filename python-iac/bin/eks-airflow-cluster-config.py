#!/usr/bin/python

import argparse
import os
import time

import lib.cloudformation as cfn
import lib.exec_ctl as exe
import lib.kubeconfig as kube
import lib.params as params
from lib.infrastructure_build_manager import InfrastructureBuildManager

ap = argparse.ArgumentParser()
ap.add_argument("--setK8Env", required=True, help="Set k8 env", default="true")
ap.add_argument("--envName", required=True, help="Required: Environment name equals environment to deploy to")

args = vars(ap.parse_args())

# Create a list of all regions of the env
paramsDir = "./params/" + args["envName"] + "/"
regions = InfrastructureBuildManager.prepare_region_builds(paramsDir, args["envName"])

# Loop through the list of regions and perform the selected action on every region
for region in regions:
    # load params into memory
    environment = InfrastructureBuildManager.get_build_environment(region, args["envName"], None)
    # params.load_params_mem(args["envName"], region)
    # Add airflow namespace
    if environment["DeployMWAA"] == "true":

        if args["setK8Env"] == "true":
            # configure kubeconfig
            clusterName = cfn.get_cluster(args["envName"], environment["Region"])
            kube.update_kubeconfig(clusterName, environment["Region"])

            # tag subnets for alb-ingress-controller automation
            eksClusterName = cfn.get_nested_name(args["envName"], "Eks", environment["Region"])
            stackName = cfn.get_nested_name(args["envName"], "Vpc", environment["Region"])

            # see if aws-auth has already been added
            eksUser = cfn.get_stack_output(eksClusterName, "EKSUserName", environment["Region"])
            eksUserArn = cfn.get_stack_output(eksClusterName, "EKSUserArn", environment["Region"])
            eksNodeInstanceRole = cfn.get_stack_output(eksClusterName, "EksNodeInstanceRole", environment["Region"])

            awsAuthCheck = "kubectl describe configmap aws-auth -n kube-system"
            status = exe.sub_process(awsAuthCheck)

            awsAuth = (
                """\
            apiVersion: v1
            kind: ConfigMap
            metadata:
              name: aws-auth
              namespace: kube-system
            data:
              mapRoles: |
                - rolearn: """
                + eksNodeInstanceRole
                + """
                  username: system:node:{{EC2PrivateDNSName}}
                  groups:
                    - system:bootstrappers
                    - system:nodes
              mapUsers: |
                - userarn: """
                + eksUserArn
                + """
                  username: """
                + eksUser
                + """
                  groups:
                    - system:masters
                    - cluster-admin
                    - tiller
            """
            )
            authfilepath = "/tmp/" + args["envName"] + "-aws-auth.yaml"
            f = open(authfilepath, "w")
            f.write(awsAuth)
            f.close()

            while os.stat(authfilepath).st_size == 0:
                time.sleep(5)
                print("Waiting for file write out")

            # add aws-auth if doesn't exist already
            if eksUser not in status:
                command = "kubectl apply -f " + authfilepath
                status = exe.sub_process(command)
                print(status)
            else:
                print("aws-auth has the following config:")
                print(status)
        # command = "kubectl get nodes -o wide"
        # status = exe.sub_process(command)
        # print(status)
        command = "kubectl get ns mwaa"
        status, msg = exe.sub_process_rc(command)
        print(msg)
        if status != 0:
            print("Creating airflow namespace")
            command = "kubectl create namespace mwaa"
            status, msg = exe.sub_process_rc(command)
            print(msg)
            command = "kubectl get ns mwaa"
            status, msg = exe.sub_process_rc(command)
            print(msg)
            config_file = os.path.abspath(
                os.path.dirname(os.path.abspath(__file__)) + "/../conf/mwaa/aws-auth-eks/role.yaml"
            )
            command = f"kubectl apply -f {config_file} -n mwaa"
            status, msg = exe.sub_process_rc(command)
            print(msg)
            command = "kubectl get pods -n mwaa --as mwaa-service"
            status, msg = exe.sub_process_rc(command)
    else:
        print(
            "DeployMWAA is false for " + args["envName"] + " env in " + region + " region, so nothing to be done here"
        )
        print("")
