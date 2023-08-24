package main

import (
	sm "aws/secretsmanager"
	"context"
	b64 "encoding/base64"
	"flag"
	"fmt"
	"io/ioutil"
	"log"
	"os"
	"path/filepath"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials/stscreds"
	"github.com/aws/aws-sdk-go-v2/service/kms"
	"github.com/aws/aws-sdk-go-v2/service/kms/types"
	"github.com/aws/aws-sdk-go-v2/service/sts"
)

var profile string = "dev"
var roleArn string = "arn:aws:iam::597609335369:role/CrossAccountDevRole"

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
		region string
	)

	flag.StringVar(&action, "action", "", "Action to take: encrypt, decrypt, delete")
	flag.StringVar(&env, "env", "", "Required: Environment file to decrypt\n Use 'local' with action=decrypt to generate .env output")
	flag.StringVar(&region, "region", "us-east-2", "Default to us-east-2")
	flag.Parse()

	cfg := Assume_role(roleArn, region)
	svc := kms.NewFromConfig(cfg)

	// exit if env isn't provided through cmd
	if env == "" {
		fmt.Println("No environment was provided")
		os.Exit(1)
	}
	// get working directory
	var keyExists bool = false
	var KeyId string
	projectName := "platform"
	path := "../secrets/" + env

	input := &kms.ListAliasesInput{}
	keys, err := svc.ListAliases(context.TODO(), input)
	if err != nil {
		log.Println("Failed to retrieve list of KMS keys: ", err)
	} else {
		for _, v := range keys.Aliases {
			if *v.AliasName == "alias/"+projectName {
				keyExists = true
				KeyId = *v.TargetKeyId
				log.Println("Found existing key:", KeyId)
			}
		}
	}

	if action == "encrypt" {

		if keyExists == false {
			// create a new key
			input := &kms.CreateKeyInput{
				KeyUsage: types.KeyUsageType(types.KeyUsageTypeEncryptDecrypt),
				Origin:   types.OriginType(types.OriginTypeAwsKms),
			}
			output, err := svc.CreateKey(context.TODO(), input)
			if err != nil {
				log.Println("Failed to create KMS key: ", err)
			} else {
				log.Println("Successful creation of KMS key")
				KeyId = *output.KeyMetadata.KeyId
				aliasName := "alias/" + projectName
				// give the key an alias name
				input := &kms.CreateAliasInput{
					AliasName:   &aliasName,
					TargetKeyId: &KeyId,
				}
				_, err := svc.CreateAlias(context.TODO(), input)
				if err != nil {
					log.Println("Failed to configure alias name for key: ", err)
				}
			}
		}

		// open file
		var files []string

		// get all .json files in secrets/env
		files, err = WalkMatch(path, "*.json")
		if err != nil {
			log.Println("failed to retrieve files: ", err)
		}

		for _, f := range files {
			file := strings.TrimSuffix(filepath.Base(f), filepath.Ext(f))
			log.Println("Encrypting file ", f)
			content, err := ioutil.ReadFile(f)
			if err != nil {
				log.Println("Failed to read file:", err)
			}

			input := &kms.EncryptInput{
				KeyId:     &KeyId,
				Plaintext: []byte(content),
			}

			result, err := svc.Encrypt(context.TODO(), input)
			if err != nil {
				log.Println("Got error encrypting data:", err)
			}

			blobString := b64.StdEncoding.EncodeToString(result.CiphertextBlob)

			out, err := os.Create(path + "/" + file + ".encrypted")
			if err != nil {
				log.Println("Filed to create file:", err)
			}
			_, err = out.WriteString(blobString)
			if err != nil {
				log.Println("Failed to write to file:", err)
			} else {
				err = os.Remove(path + "/" + file + ".json")
				if err != nil {
					log.Println("Failed to delete file:", err)
				}
			}
		}
	} else if action == "decrypt" {
		// open file
		var files []string
		// get all encrypted files in secrets/env
		files, err = WalkMatch(path, "*.encrypted")
		if err != nil {
			log.Println("failed to retrieve files: ", err)
		}

		for _, f := range files {

			file := strings.TrimSuffix(filepath.Base(f), filepath.Ext(f))
			log.Println("Decrypting file ", f)

			content, err := ioutil.ReadFile(f)
			if err != nil {
				log.Println("Failed to read file:", err)
			}

			blob, err := b64.StdEncoding.DecodeString(string(content))
			if err != nil {
				panic("error converting string to blob, " + err.Error())
			}

			input := &kms.DecryptInput{
				KeyId:          &KeyId,
				CiphertextBlob: []byte(blob),
			}

			result, err := svc.Decrypt(context.TODO(), input)
			if err != nil {
				log.Println("Got error decrypting data:", err)
			}

			out, err := os.Create(path + "/" + file + ".json")
			if err != nil {
				log.Println("Filed to create file:", err)
			}
			_, err = out.WriteString(string(result.Plaintext))
			if err != nil {
				log.Println("Failed to write to file:", err)
			} else {
				err = os.Remove(path + "/" + file + ".encrypted")
				if err != nil {
					log.Println("Failed to delete file:", err)
				}
			}
		}

	} else if action == "delete" {
		results, err := sm.ListSecrets(cfg, env)
		if err != nil {
			log.Println(err)
		}

		for _, v := range results {
			sm.DeleteSecrets(cfg, string(*v.ARN))
		}
	}
}
