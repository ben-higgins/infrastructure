package dynaConfig

import (
	dyno "aws/dynamodb"
	"log"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
)

func RestoreDynamoTables(cfg aws.Config, env, sourceEnv string) {

	tables, err := dyno.ListTables(cfg, env)

	if err != nil {
		log.Println("Failed to list tables:", err)
	} else {
		for _, t := range tables {
			if strings.Contains(t, env) {

				log.Println("Deleting table", t)
				// delete table that was created by cloudformation
				err := dyno.DeleteTable(cfg, t)
				if err != nil {
					log.Println("Failed to delete table:", err)
				} else {
					status := dyno.CheckStatus(cfg, t, "ARCHIVED") // ARCHIVED is a dummy variable. no value is returned when the table doesn't exist
					log.Println("Succesful deletion:", status)
				}

				s := strings.Split(t, ".")
				log.Println("Split name:", s[1])

				backupArn, _ := dyno.GetBackupArn(cfg, sourceEnv+"."+s[1])
				log.Println("Using backup arn to restore:", backupArn)

				err = dyno.RestoreTable(cfg, backupArn, t)
				if err != nil {
					log.Println("Failed to restore table: ", t, err)
				} else {
					_ = dyno.CheckStatus(cfg, t, "ACTIVE")
					log.Println("Restored table: ", t)
				}

			}
		}
	}
}
