package main

import (
	CFN "aws/cfn"
	EKS "aws/eks"
	IAM "aws/iam"
	"bufio"
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io/ioutil"
	"log"
	"os"
	"os/exec"
	"strings"
	PARAMS "util/params"
)

var out bytes.Buffer
var stderr bytes.Buffer
var params string

type HelmStruct []struct {
	Revision    int    `json:"revision"`
	Updated     string `json:"updated"`
	Status      string `json:"status"`
	Chart       string `json:"chart"`
	AppVersion  string `json:"app_version"`
	Description string `json:"description"`
}

func contains(elems []string, v string) bool {
	for _, s := range elems {
		if v == s {
			return true
		}
	}
	return false
}

func main() {

	var (
		action        string
		env           string
		projectName   string
		projectPrefix string
		branchName    string
		dockerImage   string
	)

	flag.StringVar(&action, "action", "", "Cloudformation action to peform. Options: deploy | rollback | delete")
	flag.StringVar(&env, "env", "", "Override the infrastructure environment to send the deployment to")
	flag.StringVar(&projectName, "projectName", "", "Name of service being deployed")
	flag.StringVar(&projectPrefix, "projectPrefix", "", "Name of github repo")
	flag.StringVar(&branchName, "branchName", "", "Name of gitHub branch")
	flag.StringVar(&dockerImage, "dockerImage", "", "Docker image to deploy")
	flag.Parse()

	// evaluate env branchName
	// this is so a microservice branch can be deployed to a different named environment
	if env == "" {
		env = branchName
	}
	// consider using namespace deployments
	//namespace := "default"

	//gitTagFile := "./params" + envName + "/gittag.params"

	// used for helm chart deployments for visual identity of projects
	var helmProjectName string
	if projectName == projectPrefix {
		helmProjectName = projectName
	} else {
		helmProjectName = projectPrefix + "-" + projectName
	}

	// build params map
	// use default if branch is not a standard
	var paramDir string
	var secretsFile string
	if _, err := os.Stat("../params/" + env); os.IsNotExist(err) {
		paramDir = "../params/default/"
		secretsFile = "default"
	} else {
		paramDir = "../params/" + env + "/"
		secretsFile = env
	}

	p := PARAMS.BuildParams(paramDir)

	for region := range p {
		// update-kubeconfig to connect to right cluster
		log.Println("Deploying to " + region)

		// get aws credientials
		cfg := IAM.Assume_role(p[region]["RoleArn"], region)
		eksClusterName := CFN.GetNestedStackName(cfg, env, "Eks")
		// exit softly if no environment to send container to
		if len(eksClusterName) == 0 {
			log.Println("### No infrastructure to deploy container to ###")
			os.Exit(0)
		}

		EKS.UpdateKubeConfig(eksClusterName, env, p[region]["RoleArn"])

		if action == "deploy" {

			var deploySecrets string
			var secretsPath string
			var helmEnvs string = ""

			//seed region and env
			helmEnvs = helmEnvs + "  ENV: " + env + "\n"
			helmEnvs = helmEnvs + "  AWS_REGION: " + region + "\n"

			// create secrets path
			if _, err := os.Stat("../../deployment/secrets"); os.IsNotExist(err) {
				secretsPath = "../../deployment/" + projectName + "/secrets/"
			} else {
				secretsPath = "../../deployment/secrets/"
			}

			// check if there are secrets to deploy
			var envPath string
			if _, err := os.Stat(secretsPath + secretsFile + ".yaml"); err == nil {
				envPath = secretsPath + secretsFile + ".yaml"
			} else if _, err := os.Stat(secretsPath + "default.yaml"); err == nil {
				envPath = secretsPath + "default.yaml"
			} else {
				envPath = ""
			}

			if envPath != "" {
				readFile, _ := os.Open(envPath)
				fileScanner := bufio.NewScanner(readFile)
				fileScanner.Split(bufio.ScanLines)

				for fileScanner.Scan() {
					helmEnvs = helmEnvs + "  " + fileScanner.Text() + "\n"
				}
			} else {
				log.Println("No environment variables found")
			}

			var helmStruct HelmStruct

			// check of the first deployment failed and needs to be removed before deploying second revision
			cmd := exec.Command("helm", "history", projectName, "--max", "1", "--output", "json")

			cmd.Stdout = &out
			cmd.Stderr = &stderr
			err := cmd.Run()

			if err != nil {
				log.Println(fmt.Sprint(err) + ": " + stderr.String())
			} else {
				json.Unmarshal([]byte(out.String()), &helmStruct)
				log.Println(helmStruct[0].Revision)

				// need to remove first failed deployment
				if helmStruct[0].Revision == 1 && (helmStruct[0].Status == "FAILED" || helmStruct[0].Status == "pending-install") {
					cmd = exec.Command("helm", "uninstall", projectName)
					response, err := cmd.Output()
					if err != nil {
						log.Println("Failed to uninstall failed deployment:", err)
						os.Exit(1)
					} else {
						log.Println("Unistalled failed deployment:", response)
					}
				}

			}

			// placeholder: capture inputted params (might not be possible with circleci)

			// placeholder: check if certficateArn exists in values.yaml

			// placeholder: check if wafAclArn exists in values.yaml

			// placehodler: multi region deployments - check if RegionActingAs exists in values.yaml, deploy cron job in single region

			// placeholder: check if DeployCloudfront exists in values.yaml then add param

			// find where helm charts are
			var helmPath string
			var helmValuesPath string
			var newContent string = ""

			if _, err := os.Stat("../../deployment/.helm/"); os.IsNotExist(err) {
				helmPath = "../../deployment/" + projectName + "/.helm/deployment_chart"
				helmValuesPath = "../../deployment/" + projectName + "/.helm/deployment_chart/values.yaml"
			} else {
				helmPath = "../../deployment/.helm/deployment_chart"
				helmValuesPath = "../../deployment/.helm/deployment_chart/values.yaml"
			}

			// add secrets as env variables to values.yaml template
			f, err := os.Open(helmValuesPath)
			if err != nil {
				log.Printf("yamlFile.Get err   #%v ", err)
			}
			defer f.Close()
			scanner := bufio.NewScanner(f)

			for scanner.Scan() {
				if strings.Contains(scanner.Text(), "envs") {
					newContent = newContent + scanner.Text() + "\n" + helmEnvs
				} else {
					newContent = newContent + scanner.Text() + "\n"
				}
			}
			if err := scanner.Err(); err != nil {
				log.Println("Error reading lines in values.yaml:", err)
			}

			err = ioutil.WriteFile(helmValuesPath, []byte(newContent), 0644)
			if err != nil {
				log.Println("Failed to write to values.yaml file:", err)
			} else {
				log.Println("Updated values.yaml file:\n", newContent)
			}

			cmd = exec.Command("helm", "upgrade", "--install",
				"--set", "region="+region,
				"--set", "container.image="+dockerImage,
				"--set", "serviceName="+helmProjectName,
				"--set", "envType="+env,
				"--set", "deploySecrets="+deploySecrets,
				"--set", "volumeMount.name="+projectName+"-env",
				//"--wait", "--timeout", "10m0s", "--debug",  // disabled for faster development
				helmProjectName,
				helmPath)

			log.Println(cmd)

			cmd.Stdout = &out
			cmd.Stderr = &stderr
			err = cmd.Run()

			if err != nil {
				log.Println(fmt.Sprint(err) + ": " + stderr.String())
			} else {
				log.Println("Deployed helm chart: ", out.String())
			}

		} else if action == "rollback" {

		} else if action == "delete" {

		} else {
			log.Println("No action was given")
		}

	}
}
