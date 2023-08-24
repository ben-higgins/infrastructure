#!/usr/bin/python

import argparse
import json
import os
import time
from subprocess import Popen, PIPE

import lib.exec_ctl as exe
import lib.params as params
import lib.secrets_manager as secrets
import lib.cloudformation as cfn
import lib.kubeconfig as kube
import lib.cloudflare as cloudflare
import lib.dns as dns

ap = argparse.ArgumentParser()
ap.add_argument(
    "--envName",
    required=True,
    help="Name equals environment to deploy to"
)

args = vars(ap.parse_args())

# Create a list of all regions of the env
paramsDir = "./params/" + args["envName"] + "/"
regions = [
    name for name in os.listdir(paramsDir)
    if os.path.isdir(os.path.join(paramsDir, name))
]

print("\n\nFor " + args["envName"] + " env, selected regions are " + ", ".join(regions))

# Loop through the list of regions and perform the selected action on every region
for region in regions:
    # load params into memory
    params.load_params_mem(args["envName"], region)

    # Check if the stack exist before attempting removal for gracious failing
    templateName = cfn.get_cluster(args["envName"], os.environ["Region"])

    # temporary fix to stop this script if eks was not deployed
    if os.environ["DeployEKS"] == "true" and templateName:
        print("Removing micro-services of " + args["envName"] + " env in " + region + " region")
        print("")

        # update-kubeconfig to connect to right cluster
        print(f"EKS Cluster Stack Name is: {templateName}")

        print("Update kubectl config with EKS Cluster Details")
        kube.update_kubeconfig(templateName, os.environ["Region"])

        print("Get list of all helm deployments")

        # Bash alternate for pipe command "helm list --short --all | grep -v alb-ingress-controller"
        p1 = Popen(["helm", "list", "--short", "--all"], stdout=PIPE)
        p2 = Popen(["grep", "-v", "alb-ingress-controller"], stdin=p1.stdout, stdout=PIPE)
        p3 = Popen(["grep", "-v", "dns-record"], stdin=p2.stdout, stdout=PIPE)
        p4 = Popen(["grep", "-v", "gloo"], stdin=p3.stdout, stdout=PIPE)
        helm_charts = p4.stdout.read().decode('UTF-8')
        print(helm_charts)

        print("Remove all helm charts")
        for chart in helm_charts.split():
            command = "helm uninstall " + chart + " --wait"
            output = exe.sub_process(command)
            print(output)

        print("Remove gloo")
        command = "helm uninstall gloo --wait"
        output = exe.sub_process(command)
        print(output)

        # Wait for some time so that all ALB of Ingress gets deleted before removing the alb-ingress-controller
        time.sleep(240)

        print("Remove dns-record")
        command = "helm uninstall dns-record --wait"
        output = exe.sub_process(command)
        print(output)

        print("Remove alb-ingress-controller")
        command = "helm uninstall alb-ingress-controller --wait"
        output = exe.sub_process(command)
        print(output)

    else:
        print("")
        print("DeployEKS is false for " + args["envName"] + " env in " + region + " region, so nothing to be done here")

