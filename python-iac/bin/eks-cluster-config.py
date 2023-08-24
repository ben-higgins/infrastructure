#!/usr/bin/python

import argparse
import os
import time

import lib.cloudformation as cfn
import lib.ec2 as ec2
import lib.exec_ctl as exe
import lib.kubeconfig as kube
import lib.params as params
from lib.infrastructure_build_manager import InfrastructureBuildManager

ap = argparse.ArgumentParser()
ap.add_argument("--envName", required=True, help="Required: Environment name equals environment to deploy to")

args = vars(ap.parse_args())

# Create a list of all regions of the env
paramsDir = "./params/" + args["envName"] + "/"

regions_sorted_list = InfrastructureBuildManager.prepare_region_builds(paramsDir, args["envName"])


# Loop through the list of regions and perform the selected action on every region
for region in regions_sorted_list:
    region_name = region["RegionName"]
    # load params into memory
    environment = InfrastructureBuildManager.get_build_environment(region_name, args["envName"], None)
    # temporary fix to stop this script if eks was not deployed
    if environment["DeployEKS"] == "true":
        print("")
        print("Configuring EKS of " + args["envName"] + " env in " + environment["Region"] + " region")
        print("")

        # configure kubeconfig
        clusterName = cfn.get_cluster(args["envName"], environment["Region"])
        kube.update_kubeconfig(clusterName, environment["Region"])

        # tag subnets for alb-ingress-controller automation
        eksClusterName = cfn.get_nested_name(args["envName"], "Eks", environment["Region"])
        stackName = cfn.get_nested_name(args["envName"], "Vpc", environment["Region"])
        PublicSubnetGroup = cfn.get_stack_output(stackName, "PublicSubnetGroup", environment["Region"])
        PrivateSubnetGroup = cfn.get_stack_output(stackName, "PrivateSubnetGroup", environment["Region"])

        # tag public subnets
        for subnet in PublicSubnetGroup.split(","):
            results = ec2.tag_subnet(subnet, "kubernetes.io/cluster/" + eksClusterName, "shared", environment["Region"])
            print(results)
            results = ec2.tag_subnet(subnet, "kubernetes.io/role/elb", "1", environment["Region"])
            print(results)
        # tag private subnets
        for subnet in PrivateSubnetGroup.split(","):
            results = ec2.tag_subnet(subnet, "kubernetes.io/cluster/" + eksClusterName, "shared", environment["Region"])
            print(results)
            results = ec2.tag_subnet(subnet, "kubernetes.io/role/internal-elb", "1", environment["Region"])
            print(results)

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
    - rolearn: arn:aws:iam::663946581577:role/SAMladmin
      username: SAMladmin
      groups:
        - system:masters
        - cluster-admin
        - tiller
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

        #### setup k8s web console

        # deploy metrics server
        command = "kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.3.6/components.yaml"
        status = exe.sub_process(command)
        print(status)

        # Deploy the Kubernetes dashboard

        command = "kubectl apply -f https://raw.githubusercontent.com/kubernetes/dashboard/v2.0.0-beta8/aio/deploy/recommended.yaml"
        status = exe.sub_process(command)
        print(status)

        # Create an eks-admin service account and cluster role binding
        rawClusterAdmin = """\
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: eks-admin
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1beta1
kind: ClusterRoleBinding
metadata:
  name: eks-admin
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
  - kind: ServiceAccount
    name: eks-admin
    namespace: kube-system
"""
        clusterfilepath = "/tmp/" + args["envName"] + "-rawClusterAdmin.yaml"
        f = open(clusterfilepath, "w")
        f.write(rawClusterAdmin)
        f.close()

        command = "kubectl apply -f " + clusterfilepath
        status = exe.sub_process(command)
        print(status)

        # cleanup files
        """if os.path.exists(authfilepath):
          os.remove(authfilepath)
      if os.path.exists(clusterfilepath):
          os.remove(clusterfilepath)"""

        # Read in the autoscaler yaml file
        with open("cluster-autoscaler-autodiscover.yaml") as file:
            autoscalerfiledata = file.read()

        # Replace the Cluster name placeholder string with cluster name
        autoscalerfiledata = autoscalerfiledata.replace("<YOUR_CLUSTER_NAME>", clusterName)

        # Cluster AutoScaler file path per EKS cluster
        autoscalerfilepath = "/tmp/" + clusterName + "-cluster-autoscaler.yaml"

        # Write the file out again
        with open(autoscalerfilepath, "w") as file:
            file.write(autoscalerfiledata)

        # Deploy the Kubernetes Cluster Autoscaler
        command = "kubectl apply -f " + autoscalerfilepath
        status = exe.sub_process(command)
        print(status)

        # Install the nvidia plugin
        command = "kubectl apply -f nvidia-plugin.yaml"
        status = exe.sub_process(command)
        print(status)

        command = f"python3 bin/eks-airflow-cluster-config.py --envName {args['envName']} --setK8Env false"
        status = exe.sub_process(command)
        print(status)

    else:
        print("DeployEKS is false for " + args["envName"] + " env in " + region + " region, so nothing to be done here")
        print("")
