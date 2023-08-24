package secretsmanager

import (
	"context"
	b64 "encoding/base64"
	"encoding/json"
	"io/ioutil"
	"log"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/kms"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager/types"
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

func ListSecrets(cfg aws.Config, env string) ([]types.SecretListEntry, error) {
	svc := secretsmanager.NewFromConfig(cfg)
	e := aws.String(env)
	i := setInt(100)

	filter := []types.Filter{
		{
			Key:    "name",
			Values: []string{*e},
		},
	}

	input := &secretsmanager.ListSecretsInput{
		Filters:    filter,
		MaxResults: i,
	}

	results, err := svc.ListSecrets(context.TODO(), input)
	if err != nil {
		log.Println("Failed to get list of secrets: ", err)
		return nil, err
	} else {
		return results.SecretList, nil
	}

}

func CreateSecrets(cfg aws.Config, secretsName, secrets, env string) {
	svc := secretsmanager.NewFromConfig(cfg)
	var fullSecretsName string = env + "/" + secretsName
	input := &secretsmanager.CreateSecretInput{
		Name:         &fullSecretsName,
		SecretString: &secrets,
	}

	response, err := svc.CreateSecret(context.TODO(), input)
	if err != nil {
		log.Println("Failed to create secrets:", err)
		// update secrets if exists
		putInput := &secretsmanager.PutSecretValueInput{
			SecretId:     &fullSecretsName,
			SecretString: &secrets,
		}
		result, err := svc.PutSecretValue(context.TODO(), putInput)
		if err != nil {
			log.Println("filed to update secrets:", err)
		} else {
			log.Println("Successful updating secrets:", result)
		}

	} else {
		log.Println("Successful creation of secrets:", response)
	}
}

func DeleteSecrets(cfg aws.Config, arn string) {
	t := setBool(true)

	svc := secretsmanager.NewFromConfig(cfg)
	input := &secretsmanager.DeleteSecretInput{
		SecretId:                   aws.String(arn),
		ForceDeleteWithoutRecovery: t,
	}

	result, err := svc.DeleteSecret(context.TODO(), input)
	if err != nil {
		log.Println("Failed to delete secret:", err)
	} else {
		log.Println("Deleted secret:", *result.ARN)
	}
}

func DecryptSecrets(cfg aws.Config, projectName, secretsPath, env string) string {
	var KeyId string
	svc := kms.NewFromConfig(cfg)
	// get kms key
	input := &kms.ListAliasesInput{}
	keys, err := svc.ListAliases(context.TODO(), input)
	if err != nil {
		log.Println("Failed to retrieve list of KMS keys: ", err)
	} else {
		for _, v := range keys.Aliases {
			if *v.AliasName == "alias/"+projectName {
				KeyId = *v.TargetKeyId
				log.Println("Found existing key:", KeyId)
			}
		}
	}
	// open secrets file
	f := secretsPath + env + ".encrypted"

	log.Println("Decrypting file ", f)

	content, err := ioutil.ReadFile(f)
	if err != nil {
		log.Println("Failed to read file:", err)
	}

	blob, err := b64.StdEncoding.DecodeString(string(content))
	if err != nil {
		panic("error converting string to blob, " + err.Error())
	}

	decryptInput := &kms.DecryptInput{
		KeyId:          &KeyId,
		CiphertextBlob: []byte(blob),
	}

	result, err := svc.Decrypt(context.TODO(), decryptInput)
	if err != nil {
		log.Println("Error decrypting data:", err)
	}

	return string(result.Plaintext)

}

func DecryptPlatformSecrets(cfg aws.Config, projectName, path string) string {
	var KeyId string
	svc := kms.NewFromConfig(cfg)
	// get kms key
	input := &kms.ListAliasesInput{}
	keys, err := svc.ListAliases(context.TODO(), input)
	if err != nil {
		log.Println("Failed to retrieve list of KMS keys: ", err)
	} else {
		for _, v := range keys.Aliases {
			if *v.AliasName == "alias/"+projectName {
				KeyId = *v.TargetKeyId
				log.Println("Found existing key:", KeyId)
			}
		}
	}
	// open secrets file

	log.Println("Decrypting file ", path)

	content, err := ioutil.ReadFile(path)
	if err != nil {
		log.Println("Failed to read file:", err)
	}

	blob, err := b64.StdEncoding.DecodeString(string(content))
	if err != nil {
		panic("error converting string to blob, " + err.Error())
	}

	decryptInput := &kms.DecryptInput{
		KeyId:          &KeyId,
		CiphertextBlob: []byte(blob),
	}

	result, err := svc.Decrypt(context.TODO(), decryptInput)
	if err != nil {
		log.Println("Error decrypting data:", err)
	}

	return string(result.Plaintext)

}

// helpers

func setInt(x int32) *int32 {
	return &x
}

func setBool(x bool) *bool {
	return &x
}
