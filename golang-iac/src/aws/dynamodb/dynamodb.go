package dynamodb

import (
	"context"
	"log"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
)

func ListTables(cfg aws.Config, env string) ([]string, error) {
	svc := dynamodb.NewFromConfig(cfg)

	input := &dynamodb.ListTablesInput{
		ExclusiveStartTableName: aws.String(env),
	}

	result, err := svc.ListTables(context.TODO(), input)
	if err != nil {
		return nil, err
	} else {
		return result.TableNames, nil
	}
}

// return arn of backup
func GetBackupArn(cfg aws.Config, backupName string) (string, error) {
	svc := dynamodb.NewFromConfig(cfg)

	input := &dynamodb.ListBackupsInput{
		TableName: aws.String("dev-1.yellowfin-submission-limits"),
	}

	var arn string
	result, err := svc.ListBackups(context.TODO(), input)
	if err != nil {
		return "", err
	} else {
		for _, backupArn := range result.BackupSummaries {
			arn = *backupArn.BackupArn
		}
		return arn, nil
	}

}

func RestoreTable(cfg aws.Config, backupArn, tableName string) error {
	svc := dynamodb.NewFromConfig(cfg)

	input := &dynamodb.RestoreTableFromBackupInput{
		BackupArn:       aws.String(backupArn),
		TargetTableName: aws.String(tableName),
	}

	_, err := svc.RestoreTableFromBackup(context.TODO(), input)
	if err != nil {
		return err
	} else {
		return nil
	}
}

func GetTableStatus(cfg aws.Config, tableName string) (string, error) {
	svc := dynamodb.NewFromConfig(cfg)

	input := &dynamodb.DescribeTableInput{
		TableName: aws.String(tableName),
	}

	result, err := svc.DescribeTable(context.TODO(), input)
	if err != nil {
		return "", err
	} else {
		return string(result.Table.TableStatus), nil
	}
}

func DeleteTable(cfg aws.Config, tableName string) error {
	svc := dynamodb.NewFromConfig(cfg)

	input := &dynamodb.DeleteTableInput{
		TableName: aws.String(tableName),
	}

	_, err := svc.DeleteTable(context.TODO(), input)
	if err != nil {
		return err
	} else {
		return nil
	}
}

func CheckStatus(cfg aws.Config, tableName, status string) string {
	// loop over TableStatus until build complete
	var dynamoStatus string

	for true {
		if dynamoStatus != status {
			time.Sleep(3 * time.Second)
			dynamoStatus, _ = GetTableStatus(cfg, tableName)
			if len(dynamoStatus) == 0 {
				log.Println("nil")
				break
			} else {
				log.Println("Table:", tableName, dynamoStatus)
			}
		} else {
			log.Println("Status:", dynamoStatus)
			break
		}
	}
	return dynamoStatus
}
