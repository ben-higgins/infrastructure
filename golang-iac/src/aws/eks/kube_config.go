package eks

import (
	"bytes"
	"fmt"
	"log"
	"os/exec"
)

// need to upgrade to https://pkg.go.dev/k8s.io/kubernetes/cmd/kubeadm/app/util/kubeconfig
func UpdateKubeConfig(eksClusterName, env, roleArn string) {
	var profile string

	// need to use an aws profile because of the multi aws accounts
	if env == "prod" {
		log.Println("not ready to deploy prod")
	} else if env == "stage" || env == "test" {
		profile = "test"
	} else {
		profile = "dev"
	}

	log.Println("Using aws profile:", profile)
	log.Println("aws", "eks", "update-kubeconfig", "--name", eksClusterName, "--profile", profile, "--role-arn", roleArn)
	cmd := exec.Command("aws", "eks", "update-kubeconfig", "--name", eksClusterName, "--profile", profile, "--role-arn", roleArn)
	response, err := cmd.Output()
	if err != nil {
		log.Println(err)
	} else {
		log.Println("Updated kubeconfig: " + string(response))
	}

	cmd = exec.Command("kubectl", "cluster-info")
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
}
