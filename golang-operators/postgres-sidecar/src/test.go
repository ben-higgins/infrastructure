package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
)

func GetSecrets(cfg aws.Config, secretsName, env string) map[string]string {
	svc := secretsmanager.NewFromConfig(cfg)

	input := &secretsmanager.GetSecretValueInput{
		SecretId: aws.String(env + "/" + secretsName),
	}
	secrets, err := svc.GetSecretValue(context.TODO(), input)
	if err != nil {
		log.Println("Failed to retrieve secrets:", err)
	}

	s := map[string]string{}
	json.Unmarshal([]byte(*secrets.SecretString), &s)
	return s
}

func main() {
	cfg, err := config.LoadDefaultConfig(
		context.TODO(),
		config.WithRegion("us-east-2"),
		config.WithSharedConfigProfile("dev"),
	)
	if err != nil {
		log.Fatalf("unable to load SDK config, %v", err)
	}

	s := GetSecrets(cfg, "postgres-rds", "eks-migration")

	for k, v := range s {
		fmt.Println(k, v)
	}
}
