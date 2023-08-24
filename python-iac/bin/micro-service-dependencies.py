#!/usr/bin/python

import argparse
import json
import os
from subprocess import Popen, PIPE

import lib.exec_ctl as exe
import lib.params as params
import lib.secrets_manager as secrets
import lib.cloudformation as cfn
import lib.kubeconfig as kube
import lib.cloudflare as cloudflare
import lib.dns as dns
from distutils import util

ap = argparse.ArgumentParser()
ap.add_argument("--envName", required=True,
                help="Name equals environment to deploy to")

args = vars(ap.parse_args())
re_elb_name_from_gateway = r'(.+?)\..+-.+'

# Create a list of all regions of the env
paramsDir = "./params/" + args["envName"] + "/"
regions = [ name for name in os.listdir(paramsDir) if os.path.isdir(os.path.join(paramsDir, name)) ]
print("")
print("For " + args["envName"] + " env, selected regions are " + ", ".join(regions))


# Loop through the list of regions and perform the selected action on every region
for region in regions:
    # load params into memory
    params.load_params_mem(args["envName"], region)

    # temporary fix to stop this script if eks was not deployed
    if os.environ["DeployEKS"] == "true":
      print("")
      print("Installing Micro-service dependencies for " + args["envName"] + " env in " + region + " region")
      print("")

      # update-kubeconfig to connect to right cluster
      print("Get EKS Cluster Name")
      clusterName = cfn.get_cluster(args["envName"], os.environ["Region"])

      print("Update kubectl config with EKS Cluster Details")
      output = kube.update_kubeconfig(clusterName, os.environ["Region"])
      print(output)
      # install redis on cluster if environment is develop
      """
      if branchName == "develop":
          command = "helm repo add bitnami https://charts.bitnami.com/bitnami"
          sub_process(command)
          command = "helm upgrade --install --wait --timeout 300 --set usePassword=false redis bitnami/redis"
      """

      print("Deploy alb-ingress-controller for web frontend containers")
      print("Adding eks-charts repo")
      # download Helm eks-charts - https://github.com/aws/eks-charts
      command = "helm repo add eks https://aws.github.io/eks-charts"
      output = exe.sub_process(command)
      print(output)

      # install required config
      output = Popen(["kubectl", "apply", "-k", "github.com/aws/eks-charts/stable/aws-load-balancer-controller//crds?ref=master"], stdout=PIPE)
      print(output.stdout.read())

      # install aws ingress controller
      print('Install aws loadbalancer controler')
      command = "helm upgrade --install --wait --timeout 60s --set clusterName=" + clusterName + " --set autoDiscoverAwsRegion=true --set autoDiscoverAwsVpcID=true --namespace kube-system alb-ingress-controller eks/aws-load-balancer-controller"
      output = exe.sub_process(command)
      print(output)

      print("Deploy solo.io api gateway")
      ## ingress https://docs.solo.io/gloo/latest/guides/integrations/ingress/
      ### deploy solo.io gloo https://docs.solo.io/gloo/latest/installation/gateway/kubernetes

      command = "helm repo add gloo https://storage.googleapis.com/solo-public-helm"
      output = exe.sub_process(command)
      print(output)

      command = "helm repo update"
      output = exe.sub_process(command)
      print(output)

      # Fetch Certificate ARN")
      output = json.loads(secrets.get_secret(args["envName"] + "/cms-ssl-certificates", os.environ["Region"]))
      for key in output:
          if key == os.environ["Region"]:
              certficateArn = output[key]
              break

      gatewayOverrides = f"""
      settings:
        watchNamespaces:
          - default
      gloo:
        logLevel: warn
      discovery:
        logLevel: warn
      gatewayProxies:
        gatewayProxy:
          gatewaySettings:
            disableHttpsGateway: true
          service:
            httpsFirst: true
            kubeResourceOverride:
              spec:
                ports:
                  - name: http
                    port: 80
                    targetPort: 8080
                  - name: https
                    port: 443
                    targetPort: 8080
            extraAnnotations:
              # https://kubernetes-sigs.github.io/aws-load-balancer-controller/v2.2/guide/service/nlb/#configuration
              service.beta.kubernetes.io/aws-load-balancer-type: "external"
              # https://kubernetes-sigs.github.io/aws-load-balancer-controller/v2.2/guide/service/nlb/
              service.beta.kubernetes.io/aws-load-balancer-scheme: internet-facing
              service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: "instance"
              service.beta.kubernetes.io/aws-load-balancer-ssl-ports: "443"
              # https://docs.aws.amazon.com/elasticloadbalancing/latest/network/create-tls-listener.html#describe-ssl-policies
              service.beta.kubernetes.io/aws-load-balancer-ssl-negotiation-policy: "ELBSecurityPolicy-TLS13-1-2-2021-06"
              service.beta.kubernetes.io/aws-load-balancer-ssl-cert: \"{certficateArn}\""""

      f = open("gatewayOverrides.yaml", "w")
      f.write(gatewayOverrides)
      f.close()

      # Deploy api gateway with Internal Classic ALB
      command = "helm upgrade --install --wait --namespace default --values gatewayOverrides.yaml gloo gloo/gloo --version 1.10.13"
      output = exe.sub_process(command)
      print(output)

      # Fetch the Gloo proxy address (ALB Name)
      command = "glooctl proxy address -n default"
      api_gateway_address = exe.sub_process(command)

      # patch gloo proxy to enable stdout traffic logs
      patch = """\
apiVersion: gateway.solo.io/v1
kind: Gateway
metadata:
  name: gateway-proxy
  namespace: default
spec:
  bindAddress: '::'
  bindPort: 8080
  proxyNames:
    - gateway-proxy
  httpGateway: {}
  useProxyProto: false
  options:
    accessLoggingService:
      accessLog:
      - fileSink:
          jsonFormat:
            httpMethod: '%REQ(:METHOD)%'
            protocol: '%PROTOCOL%'
            responseCode: '%RESPONSE_CODE%'
            clientDuration: '%DURATION%'
            targetDuration: '%RESPONSE_DURATION%'
            path: '%REQ(X-ENVOY-ORIGINAL-PATH?:PATH)%'
            upstreamName: '%UPSTREAM_CLUSTER%'
            systemTime: '%START_TIME%'
            requestId: '%REQ(X-REQUEST-ID)%'
            responseFlags: '%RESPONSE_FLAGS%'
            messageType: '%REQ(x-type)%'
            number: '%REQ(x-number)%'
          path: /dev/stdout
"""
      proxypatchfilepath = args["envName"] + "-proxy-patch.yaml"
      f = open(proxypatchfilepath, "w")
      f.write(patch)
      f.close()

      command = "kubectl apply -f " + proxypatchfilepath
      output = exe.sub_process(command)
      print(output)

      print("Deploy Datadog")
      # deploy datadog
      datadogSecret = json.loads(secrets.get_secret(args["envName"] + "/datadog", os.environ["Region"]))

      command = "helm repo add datadog https://helm.datadoghq.com"
      output = exe.sub_process(command)
      print(output)

      command = "helm repo update"
      output = exe.sub_process(command)
      print(output)


      command = ["helm", "upgrade", "--install", "datadog-agent", "datadog/datadog",
                "--set", "datadog.tags={env:" + args["envName"] + ", region:" + os.environ["Region"] + ", cluster=" + clusterName + "}",
                "--set", "datadog.site=datadoghq.com",
                "--set", "datadog.apiKey=" + datadogSecret["api_key"],
                "--set", "datadog.clusterName=" + args["envName"],
                "--set", "datadog.containerExclude='image:quay.io/solo-io/gateway image:quay.io/solo-io/discovery image:observeinc/proxy image:gcr.io/datadoghq/agent image:gcr.io/datadoghq/cluster-agent kube_namespace:kube-system kube_namespace:kube-node-lease kube_namespace:kube-public kube_namespace:kubernetes-dashboard'",
                "--set", "datadog.logs.enabled=true",
                "--set", "datadog.apm.portEnabled=true",
                "--set", "datadog.logs.containerCollectAll=true",
                "--set", "targetSystem=linux",
                "--set", "datadog.apm.port=8126",
                "--set", "datadog.serviceTopology.enabled=true"]

      # output subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)

      output = exe.sub_process(command)
      print(output)

      # add datadog kube service for ddtrace address
      ddservice = """\
---
apiVersion: v1
kind: Service
metadata:
  labels:
    app: datadog-agent
  name: datadog-agent
spec:
  type: ClusterIP
  ports:
    - name: dogstatsd
      port: 8125
      protocol: UDP
      targetPort: 8125
    - name: apm
      port: 8126
      protocol: TCP
      targetPort: 8126
  selector:
    app: datadog-agent
"""

      servicefilepath = args["envName"] + "-ddtrace-service.yaml"
      f = open(servicefilepath, "w")
      f.write(ddservice)
      f.close()

      command = "kubectl apply -f " + servicefilepath
      status = exe.sub_process(command)
      print(status)

    else:
        print("")
        print("DeployEKS is false for " + args["envName"] + " env in " + region + " region, so nothing to be done here")
