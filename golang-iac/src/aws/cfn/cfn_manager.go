package cfnManager

import (
	"context"
	"log"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/cloudformation"
	"github.com/aws/aws-sdk-go-v2/service/cloudformation/types"
)

// source https://pkg.go.dev/github.com/aws/aws-sdk-go-v2/service/cloudformation#Client.DescribeStacks
func StackStatus(cfg aws.Config, stackName string) types.StackStatus {
	svc := cloudformation.NewFromConfig(cfg)
	input := &cloudformation.DescribeStacksInput{
		StackName: aws.String(stackName),
	}
	response, err := svc.DescribeStacks(context.TODO(), input)
	if err != nil {
		log.Println(err)
	}
	var res types.StackStatus
	for _, i := range response.Stacks {
		res = i.StackStatus
	}

	return res
}

func DeleteAllStacks(cfg aws.Config, env string) {
	svc := cloudformation.NewFromConfig(cfg)

	input := &cloudformation.ListStacksInput{
		StackStatusFilter: []types.StackStatus{
			types.StackStatusCreateComplete,
			types.StackStatusCreateFailed,
			types.StackStatusRollbackInProgress,
			types.StackStatusRollbackFailed,
			types.StackStatusRollbackComplete,
			types.StackStatusUpdateComplete,
			types.StackStatusUpdateInProgress,
			types.StackStatusUpdateRollbackFailed,
			types.StackStatusUpdateRollbackComplete,
		},
	}

	response, err := svc.ListStacks(context.TODO(), input)
	if err != nil {
		log.Println("Failed to list stacks:", err)
	}

	for _, s := range response.StackSummaries {
		if strings.Contains(*s.StackName, env) {
			if s.ParentId == nil {
				log.Println(*s.StackName)
				// DeleteStack(cfg, *s.StackName)
			}
		}
	}
}

// source https://github.com/aws/aws-sdk-go-v2/blob/main/service/cloudformation/api_op_ListStacks.go
func StackExists(cfg aws.Config, envName string) bool {
	var exists bool = false
	svc := cloudformation.NewFromConfig(cfg)

	params := &cloudformation.ListStacksInput{
		StackStatusFilter: []types.StackStatus{
			types.StackStatusCreateComplete,
			types.StackStatusCreateFailed,
			types.StackStatusRollbackInProgress,
			types.StackStatusRollbackFailed,
			types.StackStatusRollbackComplete,
			types.StackStatusUpdateComplete,
			types.StackStatusUpdateInProgress,
			types.StackStatusUpdateRollbackFailed,
			types.StackStatusUpdateRollbackComplete,
		},
	}

	response, err := svc.ListStacks(context.TODO(), params)
	if err != nil {
		log.Println(err)
	}
	for _, name := range response.StackSummaries {
		if *name.StackName == envName {
			exists = true
		}
	}
	return exists
}

type keyPairs struct {
	ParameterKey   string
	ParameterValue string
}
type keyPairList struct {
	Items []keyPairs
}

func (params *keyPairList) AddItem(item keyPairs) {
	params.Items = append(params.Items, item)
}

func CreateStack(cfg aws.Config, envName, template string, paramList map[string]string, envType, region string) {
	// create a string of params
	var paramString []types.Parameter
	for key, value := range paramList {
		p := types.Parameter{ParameterKey: aws.String(key), ParameterValue: aws.String(value)}
		paramString = append(paramString, p)
	}

	svc := cloudformation.NewFromConfig(cfg)

	creq := &cloudformation.CreateStackInput{
		StackName:    aws.String(envName),
		OnFailure:    types.OnFailure("DO_NOTHING"),
		Capabilities: []types.Capability{types.CapabilityCapabilityAutoExpand, types.CapabilityCapabilityNamedIam},
		Parameters:   paramString,
		TemplateURL:  aws.String(template),
	}

	_, err := svc.CreateStack(context.TODO(), creq)
	if err != nil {
		log.Println(err)
	}

	// loop over StackStatus until build complete
	var status types.StackStatus
	for true {
		if (string(status) != "CREATE_COMPLETE") && (string(status) != "CREATE_FAILED") {
			time.Sleep(30 * time.Second)
			status = StackStatus(cfg, envName)
			log.Println(status)
		} else {
			log.Println("Stack Finished deploying with status: " + status)
			break
		}
	}
}

func UpdateStack(cfg aws.Config, envName, template string, paramList map[string]string, envType, region string) {
	// create a string of params
	var paramString []types.Parameter
	for key, value := range paramList {
		p := types.Parameter{ParameterKey: aws.String(key), ParameterValue: aws.String(value)}
		paramString = append(paramString, p)
	}

	svc := cloudformation.NewFromConfig(cfg)

	creq := &cloudformation.UpdateStackInput{
		StackName:    aws.String(envName),
		Capabilities: []types.Capability{types.CapabilityCapabilityAutoExpand, types.CapabilityCapabilityNamedIam},
		Parameters:   paramString,
		TemplateURL:  aws.String(template),
	}

	_, err := svc.UpdateStack(context.TODO(), creq)
	if err != nil {
		log.Println(err)
	}

	// loop over StackStatus until stack update completes
	var status types.StackStatus
	for true {
		if (string(status) != "UPDATE_COMPLETE") && (string(status) != "UPDATE_ROLLBACK_COMPLETE") && (string(status) != "UPDATE_FAILED") && (string(status) != "UPDATE_ROLLBACK_FAILED") {
			time.Sleep(30 * time.Second)
			status = StackStatus(cfg, envName)
			log.Println(status)
		} else {
			log.Println("Stack Finished updating with status: " + status)
			break
		}

	}
}

func DeleteStack(cfg aws.Config, envName string) {
	svc := cloudformation.NewFromConfig(cfg)

	creq := &cloudformation.DeleteStackInput{
		StackName: aws.String(envName),
	}

	_, err := svc.DeleteStack(context.TODO(), creq)
	if err != nil {
		log.Println(err)
	}

	// loop over StackStatus until stack delete completes
	var status types.StackStatus
	for true {
		if (string(status) != "DELETE_COMPLETE") && (string(status) != "DELETE_FAILED") && (string(status) != "ROLLBACK_COMPLETE") {
			time.Sleep(30 * time.Second)
			status = StackStatus(cfg, envName)
			log.Println(status)
		} else {
			log.Println("Stack Finished deleting with status: " + status)
			break
		}
	}
}

func GetStackOutputs(cfg aws.Config, stackName string) map[string]string {
	svc := cloudformation.NewFromConfig(cfg)
	res := make(map[string]string)

	input := &cloudformation.DescribeStacksInput{
		StackName: aws.String(stackName),
	}
	response, err := svc.DescribeStacks(context.TODO(), input)
	if err != nil {
		log.Println(err)
	} else {
		for _, i := range response.Stacks {
			for _, v := range i.Outputs {
				res[*v.OutputKey] = *v.OutputValue
			}
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
