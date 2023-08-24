package eksconfig

import (
	"bytes"
	"fmt"
	"io/ioutil"
	"log"
	"os"
	"os/exec"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"

	CFN "aws/cfn"
	EC2 "aws/ec2"
	SECRETS "aws/secretsmanager"
)

func ConfigureEks(cfg aws.Config, stackName string, p map[string]string) {

	// get eks cluster name (same name as cfn stack name)
	eksClusterName := CFN.GetNestedStackName(cfg, stackName, "Eks")
	vpcStackName := CFN.GetNestedStackName(cfg, stackName, "Vpc")
	vpcStackOutput := CFN.GetStackOutputs(cfg, vpcStackName)

	for _, i := range strings.Split(vpcStackOutput["PublicSubnetGroup"], ",") {
		EC2.CreateTags(cfg, i, "kubernetes.io/cluster/"+eksClusterName, "shared")
		EC2.CreateTags(cfg, i, "kubernetes.io/role/elb", "1")
	}

	for _, i := range strings.Split(vpcStackOutput["PrivateSubnetGroup"], ",") {
		EC2.CreateTags(cfg, i, "kubernetes.io/cluster/"+eksClusterName, "shared")
		EC2.CreateTags(cfg, i, "kubernetes.io/role/internal-elb", "1")
	}

	// add permissions to allow users access to eks cluster
	eksStackOutput := CFN.GetStackOutputs(cfg, eksClusterName)

	// based on evironment name, select the dev role to allow access to eks to engineering
	roleArn := map[string]string{
		"dev":     "arn:aws:iam::597609335369:role/CrossAccountDevRole",
		"testing": "arn:aws:iam::597609335369:role/CrossAccountDevRole",
		"qa":      "arn:aws:iam::667813852149:role/CrossAccountDevRole",
		"test":    "arn:aws:iam::667813852149:role/CrossAccountDevRole",
		"staging": "arn:aws:iam::667813852149:role/CrossAccountDevRole",
		"main":    "arn:aws:iam::394007061642:role/CrossAccountDevRole",
	}

	var role string
	if roleArn[p["Name"]] == "" {
		//default to dev if this is an edge environment name
		role = "arn:aws:iam::597609335369:role/CrossAccountDevRole"
	} else {
		role = roleArn[p["Name"]]
	}

	data := []byte(`
apiVersion: v1
kind: ConfigMap
metadata:
  name: aws-auth
  namespace: kube-system
data:
  mapRoles: |
    - rolearn: ` + eksStackOutput["EksNodeInstanceRole"] + `
      username: system:node:{{EC2PrivateDNSName}}
      groups:
        - system:bootstrappers
        - system:nodes
    - rolearn: ` + role + `
      username: SAMladmin
      groups:
        - system:masters
        - cluster-admin
  mapUsers: |
    - userarn: ` + eksStackOutput["EKSUserArn"] + `
      username: ` + eksStackOutput["EKSUserName"] + `
      groups:
        - system:masters
        - cluster-admin
    `)

	// check if configmap aws-auth already exists
	// not sure if it's needed

	err := os.WriteFile("/tmp/aws-auth.yaml", data, 0644)
	if err != nil {
		log.Println(err)
	}

	cmd := exec.Command("kubectl", "apply", "-f", "/tmp/aws-auth.yaml")
	//response, err := cmd.Output()
	var out bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &stderr
	err = cmd.Run()

	if err != nil {
		log.Println(fmt.Sprint(err) + ": " + stderr.String())
		//log.Println(err)
	} else {
		log.Println("Applied kube template: " + out.String())
	}

	// deploy metrics server
	cmd = exec.Command("kubectl", "apply", "-f", "https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml")
	response, err := cmd.Output()
	if err != nil {
		log.Println(err)
	} else {
		log.Println("Deployed metrics server: " + string(response))
	}

	// deploy kubernetes dashboard
	cmd = exec.Command("kubectl", "apply", "-f", "https://raw.githubusercontent.com/kubernetes/dashboard/v2.7.0/aio/deploy/recommended.yaml")
	response, err = cmd.Output()
	if err != nil {
		log.Println(err)
	} else {
		log.Println("Deployed kubernetes dashboard: " + string(response))
	}

	// Install the nvidia plugin
	cmd = exec.Command("kubectl", "apply", "-f", "../conf/kube/nvidia-plugin.yaml")
	response, err = cmd.Output()
	if err != nil {
		log.Println(err)
	} else {
		log.Println("Deployed nvidia plugin: " + string(response))
	}

	// Cluster AutoScaler file path per EKS cluster
	input, err := ioutil.ReadFile("../conf/kube/cluster-autoscaler-autodiscover.yaml")
	if err != nil {
		log.Println(err)
	}

	output := bytes.Replace(input, []byte("<YOUR_CLUSTER_NAME>"), []byte("something"), -1)

	err = os.WriteFile("/tmp/autoscaling.yaml", output, 0644)
	if err != nil {
		log.Println(err)
	}

	cmd = exec.Command("kubectl", "apply", "-f", "/tmp/autoscaling.yaml")
	response, err = cmd.Output()
	if err != nil {
		log.Println(err)
	} else {
		log.Println("Applied autoscaling template: " + string(response))
	}

	data = []byte(`
apiVersion: v1
kind: ServiceAccount
metadata:
  name: eks-admin
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
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
`)

	err = os.WriteFile("/tmp/serviceaccount.yaml", data, 0644)
	if err != nil {
		log.Println(err)
	}

	cmd = exec.Command("kubectl", "apply", "-f", "/tmp/serviceaccount.yaml")
	response, err = cmd.Output()
	if err != nil {
		log.Println(err)
	} else {
		log.Println("Applied Service Account template: " + string(response))
	}

	// Download eks charts
	cmd = exec.Command("helm", "repo", "add", "eks", "https://aws.github.io/eks-charts")
	response, err = cmd.Output()
	if err != nil {
		log.Println(err)
	} else {
		log.Println("Installed eks charts:", string(response))
	}

	// install required config
	cmd = exec.Command("kubectl", "apply", "-f", "github.com/aws/eks-charts/stable/aws-load-balancer-controller//crds?ref=master")
	response, err = cmd.Output()
	if err != nil {
		log.Println(err)
	} else {
		log.Println("Installed aws alb controller library: " + string(response))
	}

	// deploy aws alb controller
	cmd = exec.Command("helm", "upgrade", "--install", "--wait", "--timeout", "60s", "--set", "clusterName="+eksClusterName, "--set", "autoDiscoverAwsRegion=true", "--set", "autoDiscoverAwsVpcID=true", "--namespace", "kube-system", "alb-ingress-controller", "eks/aws-load-balancer-controller")
	response, err = cmd.Output()
	if err != nil {
		log.Println(err)
	} else {
		log.Println("Deployed aws alb controller: " + string(response))
	}

	// set docker hub creds
	cmd = exec.Command("kubectl", "create", "secret", "docker-registry", "regcred", "--docker-username="+os.Getenv("DOCKER_USER"), "--docker-password="+os.Getenv("DOCKER_PASS"))
	//response, err = cmd.Output()
	cmd.Stdout = &out
	cmd.Stderr = &stderr
	err = cmd.Run()

	if err != nil {
		log.Println(fmt.Sprint(err) + ": " + stderr.String())
		//log.Println(err)
	} else {
		log.Println("Applied kube template: " + out.String())
	}

	// add solo to library
	cmd = exec.Command("helm", "repo", "add", "gloo", "https://storage.googleapis.com/solo-public-helm")
	response, err = cmd.Output()
	if err != nil {
		log.Println(err)
	} else {
		log.Println("Added gloo library to helm: " + string(response))
	}

	// add solo to library
	cmd = exec.Command("helm", "repo", "update")
	response, err = cmd.Output()
	if err != nil {
		log.Println(err)
	} else {
		log.Println("Deployed aws alb controller: " + string(response))
	}

	// add solo to library
	cmd = exec.Command("helm", "repo", "update")
	response, err = cmd.Output()
	if err != nil {
		log.Println(err)
	} else {
		log.Println("Deployed aws alb controller: " + string(response))
	}

	// get certificate arn
	var certArn string
	s := SECRETS.GetSecrets(cfg, "cms-ssl-certificates", stackName)
	for k, v := range s {
		if k == stackName {
			certArn = v
		}
	}

	gatewayOverrides := []byte(`
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
        service.beta.kubernetes.io/aws-load-balancer-ssl-cert: ` + certArn + `
        # https://docs.aws.amazon.com/elasticloadbalancing/latest/network/create-tls-listener.html#describe-ssl-policies
        service.beta.kubernetes.io/aws-load-balancer-ssl-negotiation-policy: "ELBSecurityPolicy-TLS13-1-2-2021-06"`)

	err = os.WriteFile("/tmp/gatewayoverrides.yaml", gatewayOverrides, 0644)
	if err != nil {
		log.Println(err)
	}

	cmd = exec.Command("helm", "upgrade", "--install", "--wait", "--namespace", "default", "--values", "/tmp/gatewayoverrides.yaml", "gloo", "gloo/gloo", "--version", "1.10.13")
	log.Println(cmd)
	cmd.Stdout = &out
	cmd.Stderr = &stderr
	err = cmd.Run()

	if err != nil {
		log.Println(fmt.Sprint(err) + ": " + stderr.String())
		//log.Println(err)
	} else {
		log.Println("Deployed gloo api gateway: " + out.String())
	}

	// patch gloo to enable logging
	patch := []byte(`
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
          path: /dev/stdout`)

	err = os.WriteFile("/tmp/patch.yaml", []byte(patch), 0644)
	if err != nil {
		log.Println(err)
	}

	cmd = exec.Command("kubectl", "apply", "-f", "/tmp/patch.yaml")
	log.Println(cmd)
	cmd.Stdout = &out
	cmd.Stderr = &stderr
	err = cmd.Run()

	if err != nil {
		log.Println(fmt.Sprint(err) + ": " + stderr.String())
		//log.Println(err)
	} else {
		log.Println("Patched gloo api gateway: " + out.String())
	}

	// add datadog to library
	cmd = exec.Command("helm", "repo", "add", "datadog", "https://helm.datadoghq.com")
	response, err = cmd.Output()
	if err != nil {
		log.Println(err)
	} else {
		log.Println("Added datadog repo to helm: " + string(response))
	}

	// get certificate arn
	var ddKey string
	s = SECRETS.GetSecrets(cfg, "datadog", stackName)
	for k, v := range s {
		if k == "datadog_key" {
			ddKey = v
		}
	}

	cmd = exec.Command(
		"helm", "upgrade", "--install", "datadog-agent", "datadog/datadog",
		"--set", "datadog.tags={env:"+stackName+", region:"+vpcStackOutput["Region"]+", cluster="+eksClusterName+"}",
		"--set", "datadog.site=datadoghq.com",
		"--set", "datadog.apiKey="+ddKey,
		"--set", "datadog.clusterName="+stackName,
		"--set", "datadog.containerExclude='image:quay.io/solo-io/gateway image:quay.io/solo-io/discovery image:observeinc/proxy image:gcr.io/datadoghq/agent image:gcr.io/datadoghq/cluster-agent kube_namespace:kube-system kube_namespace:kube-node-lease kube_namespace:kube-public kube_namespace:kubernetes-dashboard'",
		"--set", "datadog.logs.enabled=true",
		"--set", "datadog.apm.portEnabled=true",
		"--set", "datadog.logs.containerCollectAll=true",
		"--set", "targetSystem=linux",
		"--set", "datadog.apm.port=8126",
		"--set", "datadog.serviceTopology.enabled=true")

	response, err = cmd.Output()
	if err != nil {
		log.Println(err)
	} else {
		log.Println("Deployed Datadog to eks cluster: " + string(response))
	}

	// add datadog trace service
	ddtrace := []byte(`
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
	`)

	err = os.WriteFile("/tmp/ddtrace.yaml", []byte(ddtrace), 0644)
	if err != nil {
		log.Println(err)
	}

	cmd = exec.Command("kubectl", "apply", "-f", "/tmp/ddtrace.yaml")
	response, err = cmd.Output()
	if err != nil {
		log.Println(err)
	} else {
		log.Println("Added dd trace service: " + string(response))
	}

}
