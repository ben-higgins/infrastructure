package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"os/exec"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials/stscreds"
	"github.com/aws/aws-sdk-go-v2/service/cloudformation"
	"github.com/aws/aws-sdk-go-v2/service/sts"
)

func GetStackOutputs(cfg aws.Config, stackName string) map[string]string {
	svc := cloudformation.NewFromConfig(cfg)

	input := &cloudformation.DescribeStacksInput{
		StackName: aws.String(stackName),
	}
	response, err := svc.DescribeStacks(context.TODO(), input)
	if err != nil {
		log.Println(err)
	}
	res := make(map[string]string)

	for _, i := range response.Stacks {
		for _, v := range i.Outputs {
			res[*v.OutputKey] = *v.OutputValue
		}
	}

	return res
}

func GetStackName(cfg aws.Config, stackId string) string {
	svc := cloudformation.NewFromConfig(cfg)

	input := &cloudformation.DescribeStacksInput{
		StackName: aws.String(stackId),
	}
	response, err := svc.DescribeStacks(context.TODO(), input)
	if err != nil {
		log.Println(err)
	}
	var res string
	for _, i := range response.Stacks {
		res = *i.StackName
	}

	return res
}

func GetNestedStackName(cfg aws.Config, envName, NestedKey string) string {
	outputs := GetStackOutputs(cfg, envName)
	var res string
	for k, v := range outputs {
		if k == NestedKey {
			res = GetStackName(cfg, v)
		}
	}

	return res
}

func Assume_role(roleArn, region string) aws.Config {
	log.Println("Working in region: " + region)
	cfg, err := config.LoadDefaultConfig(context.TODO(), config.WithRegion(region))
	if err != nil {
		log.Fatalf("unable to load SDK config, %v", err)
	}

	stsSvc := sts.NewFromConfig(cfg)
	creds := stscreds.NewAssumeRoleProvider(stsSvc, roleArn)

	cfg.Credentials = aws.NewCredentialsCache(creds)

	return cfg
}

func main() {
	var (
		r string
		e string
	)

	flag.StringVar(&r, "r", "", "Region to authenticate to")
	flag.StringVar(&e, "e", "", "Deployed EKS Environment")
	flag.Parse()

	if e == "" {
		fmt.Println("Need to provide at least -env\nFor more information eks-auth -h")
		os.Exit(1)
	}
	/* this will be needed when the role changes for circleci and engineers
	if env == "default" {
		// backup credentials file
		if _, err := os.Stat(os.Getenv("$HOME") + "/.aws/credentials.backup"); err == nil {
			source, err := os.Open(os.Getenv("$HOME") + "/.aws/credentials.backup")
			if err != nil {
				fmt.Println(err)
			}
			defer source.Close()

			destination, err := os.Create(os.Getenv("$HOME") + "/.aws/credentials")
			if err != nil {
				fmt.Println(err)
			}
			defer destination.Close()
			fmt.Println("Restored personal aws keys")
		}

	} else {
	*/
	// need to use an aws profile because of the multi aws accounts
	// todo: get the arn from .aws/config
	var roleArn, profile string

	if e == "prod" {
		roleArn = "arn:aws:iam::394007061642:role/CrossAccountDevRole"
		profile = "prod"
	} else if (e == "staging") || (e == "test") {
		roleArn = "arn:aws:iam::667813852149:role/CrossAccountDevRole"
		profile = "test"
	} else {
		roleArn = "arn:aws:iam::597609335369:role/CrossAccountDevRole"
		profile = "dev"
	}

	//Call the assume_role method of the STSConnection object and pass the role
	cfg := Assume_role(roleArn, r)

	// backup credentials file
	/*
		if _, err := os.Stat(os.Getenv("HOME") + "/.aws/credentials.backup"); err != nil {
			source, err := os.Open(os.Getenv("HOME") + "/.aws/credentials")
			if err != nil {
				fmt.Println(err)
			}
			defer source.Close()

			destination, err := os.Create(os.Getenv("HOME") + "/.aws/credentials.backup")
			if err != nil {
				fmt.Println(err)
			}
			defer destination.Close()
			fmt.Println("Made backup of aws crendentials file")
		}
	*/
	// get nested stack name
	eksClusterName := GetNestedStackName(cfg, e, "Eks")
	/*
		outputs := GetStackOutputs(cfg, eksClusterName)

		// write new eks user keys to credentials file

			f, _ := os.OpenFile(os.Getenv("HOME")+"/.aws/credentials", os.O_RDWR|os.O_CREATE|os.O_TRUNC, 0644)

			f.WriteString("[default]\n")
			f.WriteString("aws_access_key_id = " + outputs["AccessKey"] + "\n")
			f.WriteString("aws_secret_access_key = " + outputs["AccessSecret"] + "\n")
	*/
	cmd := exec.Command("aws", "eks", "update-kubeconfig", "--name", eksClusterName, "--profile", profile)
	response, err := cmd.Output()
	if err != nil {
		log.Println(err)
	} else {
		log.Println("Updated kubeconfig: " + string(response))
	}

}
