package main

import (
	"bufio"
	"bytes"
	"flag"
	"io/ioutil"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	CFN "aws/cfn"
	KUBECONF "aws/eks"
	IAM "aws/iam"
	S3 "aws/s3"
	SECRETS "aws/secretsmanager"
	DYNA "util/dyna-config"
	CONF "util/eks-config"
	PARAMS "util/params"
)

var out bytes.Buffer
var stderr bytes.Buffer

func WalkMatch(root, pattern string) ([]string, error) {
	var matches []string
	err := filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() {
			return nil
		}
		if matched, err := filepath.Match(pattern, filepath.Base(path)); err != nil {
			return err
		} else if matched {
			matches = append(matches, path)
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	return matches, nil
}

func main() {
	var (
		action string
		env    string
	)

	flag.StringVar(&action, "action", "", "Cloudformation action to peform. Options: create | delete")
	flag.StringVar(&env, "env", "", "Environment to build or Delete")
	flag.Parse()

	gitHash := "SIGBI4Q0Q8AF7" // need to get git branch hash value and tag in a prefix file to checkout hash before running main.go
	gitTag := "v0.0.0"

	// build params map
	// use default if branch is not a standard
	var paramDir string
	var path string
	if _, err := os.Stat("../params/" + env); os.IsNotExist(err) {
		paramDir = "../params/default/"
		path = "../secrets/default"
	} else {
		paramDir = "../params/" + env + "/"
		path = "../secrets/" + env
	}
	//gitTagFile := "./params" + envName + "/gittag.params"

	p := PARAMS.BuildParams(paramDir)
	bucket := "platform-infrastructure-deployment-berxi"

	if action == string("deploy") {
		// deploy based on regions in map
		for region := range p {
			log.Println("Deploying to " + region)

			// get aws credientials
			cfg := IAM.Assume_role(p[region]["RoleArn"], region)

			// create s3 bucket
			S3.CreateBucket(cfg, bucket, region)

			// push cfn to bucket
			files, err := ioutil.ReadDir("../cfn")
			if err != nil {
				log.Fatal(err)
			}

			for _, f := range files {
				path := "../cfn/" + f.Name()
				log.Printf("Uploding %s to s3 buckt %s", path, bucket)
				err := S3.S3PutObject(cfg, bucket, env+"/"+gitHash, path, f.Name())
				if err != nil {
					log.Println("Failed to upload file to s3:", err)
				}
			}

			// push secrets
			var secretsFiles []string
			// get all encrypted files in secrets/env
			secretsFiles, err = WalkMatch(path, "*.encrypted")
			if err != nil {
				log.Println("failed to retrieve files: ", err)
			}

			for _, f := range secretsFiles {
				// decrypt secrets
				secrets := SECRETS.DecryptPlatformSecrets(cfg, "platform", f)

				// upload secrets to secrets manager
				rawFile := f[:len(f)-len(filepath.Ext(f))]
				fileName := rawFile[strings.LastIndex(rawFile, "/")+1:]
				SECRETS.CreateSecrets(cfg, fileName, secrets, env)
			}

			// create params list for cloudformation
			// first add params that were not pulled from param files
			p[region]["GitTag"] = gitTag
			p[region]["DeployBucketPrefix"] = gitHash
			p[region]["Name"] = env
			p[region]["Region"] = region
			p[region]["Bucket"] = bucket

			// get datadog api key for datagdog forwarder cfn template
			dd := SECRETS.GetSecrets(cfg, "platform-keys", env)
			p[region]["DatadogApiKey"] = dd["DD_API_KEY"]

			// params for building cfn
			template := "https://" + bucket + ".s3." + region + ".amazonaws.com/" + env + "/" + gitHash + "/composite.template.yaml"

			stackStatus := CFN.StackExists(cfg, env)

			if stackStatus {
				// update stack
				log.Println("Stack exists, performing a stack update")
				log.Println(template)
				CFN.UpdateStack(cfg, env, template, p[region], p[region]["Name"], region)
			} else {
				log.Println("Stack does not exists, creating now")
				CFN.CreateStack(cfg, env, template, p[region], p[region]["Name"], region)
			}

			// eks config if eks stack exists
			if p[region]["DeployEKS"] == "true" {
				// update kubeconfig
				eksClusterName := CFN.GetNestedStackName(cfg, env, "Eks")
				KUBECONF.UpdateKubeConfig(eksClusterName, env, p[region]["RoleArn"])

				CONF.ConfigureEks(cfg, env, p[region])
				if p[region]["RestoreSource"] != "" {
					DYNA.RestoreDynamoTables(cfg, env, "develop")
				}
			}

		}
	} else if action == "delete" {
		for region := range p {
			log.Println("Deleting environment " + env)

			// get aws credientials
			cfg := IAM.Assume_role(p[region]["RoleArn"], region)

			// delete all deployments in eks so that stacks can be deleted
			cmd := exec.Command("bash", "-c", "helm list | awk 'NR>1{print $1}' > /tmp/helm-list.txt")

			cmd.Stdout = &out
			cmd.Stderr = &stderr
			err := cmd.Run()

			if err != nil {
				log.Println(err, ": ", stderr.String())
			} else {
				readFile, _ := os.Open("/tmp/helm-list.txt")
				fileScanner := bufio.NewScanner(readFile)
				fileScanner.Split(bufio.ScanLines)

				for fileScanner.Scan() {
					cmd := exec.Command("helm", "uninstall", fileScanner.Text())
					cmd.Stdout = &out
					cmd.Stderr = &stderr
					err = cmd.Run()

					if err != nil {
						log.Println(err, ": ", stderr.String())
					}
					log.Println("Uninstalled Helm Chart:", fileScanner.Text())
				}
			}

			// delete all stacks (including non-nested)
			CFN.DeleteAllStacks(cfg, env)

			// delete s3 bucket
			S3.DeleteBucket(cfg, bucket)

			log.Println("Finished Deleting environment", env)
		}
	} else {
		log.Println("No action was provided")
	}
}
