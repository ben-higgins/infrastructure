package main

import (
	"archive/zip"
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"flag"
	"os/exec"

	//"go/types"
	"io"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/s3"
	"github.com/aws/aws-sdk-go/service/s3/s3manager"
	_ "github.com/lib/pq"

	conf_v2 "github.com/aws/aws-sdk-go-v2/config"
	secrets_v2 "github.com/aws/aws-sdk-go-v2/service/secretsmanager"
)

func NewSession(region string) *session.Session {
	log.Println("Working in region: " + region)

	sess, err := session.NewSessionWithOptions(session.Options{
		Profile: "default",
		Config: aws.Config{
			Region: aws.String(region),
		},
	})

	if err != nil {
		log.Printf("Failed to initialize new session: %v", err)
	}

	return sess

}

func UploadFile(sess *session.Session, filePath, bucketName string, key string) error {
	uploader := s3manager.NewUploader(sess)

	file, err := os.Open(filePath)
	if err != nil {
		return err
	}

	defer file.Close()
	_, err = uploader.Upload(&s3manager.UploadInput{
		Bucket: aws.String(bucketName),
		Key:    aws.String(key),
		Body:   file,
	})
	if err != nil {
		return err
	}

	log.Println("File uploaded:", filePath)
	return nil
}

func DownloadFile(sess *session.Session, bucketName string, key string) (string, error) {

	downloader := s3manager.NewDownloader(sess)
	fullName := key[strings.LastIndex(key, "/")+1:]

	file, err := os.Create("/tmp/" + fullName)
	if err != nil {
		log.Println("Failed to create file: ", err)
	}

	defer file.Close()

	_, err = downloader.Download(
		file,
		&s3.GetObjectInput{
			Bucket: aws.String(bucketName),
			Key:    aws.String(key),
		},
	)
	if err != nil {
		log.Println("Failed to download file: ", err)
	}

	return "/tmp/" + fullName, err
}

func ListS3Objects(sess *session.Session, bucketName, path string) (*s3.ListObjectsV2Output, error) {
	client := s3.New(sess)

	res, err := client.ListObjectsV2(&s3.ListObjectsV2Input{
		Bucket: aws.String(bucketName),
		Prefix: aws.String(path),
	})

	if err != nil {
		return nil, err
	}

	return res, err
}

func Unzip(src, dest string) error {
	r, err := zip.OpenReader(src)
	if err != nil {
		return err
	}
	defer func() {
		if err := r.Close(); err != nil {
			panic(err)
		}
	}()

	os.MkdirAll(dest, 0755)

	// Closure to address file descriptors issue with all the deferred .Close() methods
	extractAndWriteFile := func(f *zip.File) error {
		rc, err := f.Open()
		if err != nil {
			return err
		}
		defer func() {
			if err := rc.Close(); err != nil {
				panic(err)
			}
		}()

		path := filepath.Join(dest, f.Name)

		// Check for ZipSlip (Directory traversal)
		if !strings.HasPrefix(path, filepath.Clean(dest)+string(os.PathSeparator)) {
			return log.Errorf("illegal file path: %s", path)
		}

		if f.FileInfo().IsDir() {
			os.MkdirAll(path, f.Mode())
		} else {
			os.MkdirAll(filepath.Dir(path), f.Mode())
			f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, f.Mode())
			if err != nil {
				return err
			}
			defer func() {
				if err := f.Close(); err != nil {
					panic(err)
				}
			}()

			_, err = io.Copy(f, rc)
			if err != nil {
				return err
			}
		}
		return nil
	}

	for _, f := range r.File {
		err := extractAndWriteFile(f)
		if err != nil {
			return err
		}
	}

	return nil
}

func Zip(src, fileName string) error {

	dest := "/tmp/" + fileName + ".zip"
	log.Println("creating zip archive...")
	archive, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer archive.Close()
	zipWriter := zip.NewWriter(archive)

	log.Println("opening first file...")
	f, err := os.Open(src)
	if err != nil {
		return err
	}
	defer f.Close()

	log.Println("writing first file to archive...")
	w, err := zipWriter.Create(fileName + ".sql")
	if err != nil {
		return err
	}
	if _, err := io.Copy(w, f); err != nil {
		return err
	}

	zipWriter.Close()

	return nil
}

func GetSecrets(secretsName, env, region string) {
	cfg, err := conf_v2.LoadDefaultConfig(
		context.TODO(),
		conf_v2.WithRegion(region),
	)
	if err != nil {
		log.Fatalf("unable to load SDK config, %v", err)
	}

	svc := secrets_v2.NewFromConfig(cfg)

	input := &secrets_v2.GetSecretValueInput{
		SecretId: aws.String(env + "/" + secretsName),
	}
	secrets, err := svc.GetSecretValue(context.TODO(), input)
	if err != nil {
		log.Println("Failed to retrieve secrets:", err)
	}

	var s map[string]json.RawMessage
	err = json.Unmarshal([]byte(*secrets.SecretString), &s)
	if err != nil {
		log.Println(err, "Error: Failed to retrieve secrets")
	} else {
		for k, v := range s {
			os.Setenv(k, strings.Replace(string(v), "\"", "", 2))
		}
	}
}

func main() {
	// take args
	var (
		action string
		env    string
		bucket string
	)

	flag.StringVar(&action, "action", "", "backup or restore")
	flag.StringVar(&env, "env", "", "Environment name")
	flag.StringVar(&bucket, "bucket", "berxi-platform-backups-us-east-2", "bucket containing backup")

	flag.Parse()

	GetSecrets("postgres-rds", env, os.Getenv("AWS_REGION"))

	host := os.Getenv("host")
	user := os.Getenv("username")
	pass := os.Getenv("password")
	region := os.Getenv("AWS_REGION")

	// authenticate with aws
	sess := NewSession(region)

	log.Println("Pg Host address:", host)

	// get latest backup from s3
	now := time.Now()

	if action == "restore" {

		// first check if env has any backups, if not then use develop's
		log.Println("checking the following path: databases/postgres/" + env)
		var path string
		o, err := ListS3Objects(sess, bucket, "databases/postgres/"+env)
		if err != nil {
			log.Println("failed to list objects: ", err)
		}
		if len(o.Contents) == 0 {
			log.Println("Nothing in path databases/postgres/" + env + "/. Defaulting to develop")
			path = "databases/postgres/develop"
		} else {
			path = "databases/postgres/" + env
		}

		// check for a backup starting with previous day
		var i int = 0
		for true {
			i = i - 1
			back := now.AddDate(0, 0, i)
			newDate := back.Format("01-02-2006")

			log.Println("Checking file path: ", path+"/"+newDate+"/")
			o, err := ListS3Objects(sess, bucket, path+"/"+newDate+"/")
			if err != nil {
				log.Println("Failed to list objects:", err)
			}

			log.Print(o.Contents)
			if len(o.Contents) > 1 {
				for _, v := range o.Contents {
					log.Println(*v.Key)
					// the S3GetObject returns the directory as a value so need to skip the first value
					if strings.Contains(*v.Key, ".zip") {
						filePath, _ := DownloadFile(sess, bucket, *v.Key)
						// if err != nil {
						// 	log.Println("Error downloading from s3:", err)
						// }

						trimmedName := strings.TrimRight(filePath, ".zip")
						trimmedName = trimmedName[strings.LastIndex(trimmedName, "/")+1:]
						// unzip file
						err := Unzip(filePath, "/tmp/"+trimmedName)
						if err != nil {
							log.Println("Failed to unzip file:", err)
						}

						// connect to postgres instance
						psqlconn := log.Sprintf("host=%s port=%d user=%s password=%s dbname=%s sslmode=require",
							host,
							5432,
							user,
							pass,
							"postgres")

						// open database
						db, err := sql.Open("postgres", psqlconn)
						if err != nil {
							log.Println("Failed to connect to postgres:", err)
						}

						// close database
						defer db.Close()

						// check db
						err = db.Ping()
						if err != nil {
							log.Println("Ping of db failed:", err)
						}

						log.Println(trimmedName)
						// check if db already exists
						rows, err := db.Query("SELECT datname FROM pg_database")
						if err != nil {
							log.Println("Failed to query postgres db for existing databases:", err)
						}

						defer rows.Close()
						var dbExists bool = false
						for rows.Next() {
							var datname string

							err = rows.Scan(&datname)
							if err != nil {
								log.Println(err)
							}

							if datname == trimmedName {
								dbExists = true
							}
						}

						if !dbExists {
							var out bytes.Buffer
							var stderr bytes.Buffer
							// restore database
							log.Println("Restoring database: ", trimmedName)
							// create db
							_, err := db.Exec(`CREATE DATABASE "` + trimmedName + `"`)
							if err != nil {
								log.Println("Failed to create database: ", err)
							} else {

								// exec sql
								cmd := exec.Command("psql", "--dbname=postgresql://"+user+":"+pass+"@"+host+":5432/"+trimmedName,
									"--file=/tmp/"+trimmedName+"/"+trimmedName+".sql")

								log.Println(cmd)

								cmd.Stdout = &out
								cmd.Stderr = &stderr
								err = cmd.Run()

								if err != nil {
									log.Println(log.Sprint(err) + ": " + stderr.String())
									// if the restore failed, remove the created database so we don't have an orphaned db out there
									_, err := db.Exec(`DROP DATABASE "` + trimmedName + `"`)
									if err != nil {
										log.Println("Failed to drop database: ", err)
									} else {
										log.Println("Successfully rolled back creation of database: ", trimmedName)
									}
								} else {
									log.Println("Restored Database: ", out.String())
								}
							}

						} else {
							log.Println("Database already exists, skipping restore: ", trimmedName)
						}

					}
				}
				break
			}

			if i == -31 {
				log.Println("Failed to find any backups for the past 31 days")
				os.Exit(1)
			}
		}
	} else if action == "backup" {
		date := now.Format("01-02-2006")
		log.Print(date)

		// connect to postgres instance
		psqlconn := log.Sprintf("host=%s port=%d user=%s password=%s dbname=%s sslmode=require",
			host,
			5432,
			user,
			pass,
			"postgres")

		// open database
		db, err := sql.Open("postgres", psqlconn)
		if err != nil {
			log.Println("Failed to connect to postgres:", err)
		}

		// close database
		defer db.Close()

		// check db
		err = db.Ping()
		if err != nil {
			log.Println("Ping of db failed:", err)
		}

		// get a list of databases from the postgres database
		rows, err := db.Query("SELECT datname FROM pg_database WHERE datname NOT IN ('admin', 'postgres', 'template0', 'template1')")
		if err != nil {
			log.Println("Failed to query postgres db for existing databases:", err)
		}

		defer rows.Close()
		for rows.Next() {
			var datname string

			err = rows.Scan(&datname)
			if err != nil {
				log.Println(err)
			}
			// backup database
			dump := "/tmp/" + datname + "/" + datname + ".sql"
			err := exec.Command("pg_dump", "--dbname=postgresql://"+user+":"+pass+"@"+host+":5432/"+datname, "--file="+dump)
			if err != nil {
				log.Println("Failed to dump database:", datname, err)
			}

			// zip file
			ziperr := Zip(dump, datname)
			if ziperr != nil {
				log.Println("failed to zip file:", ziperr)
			}

			// upload file
			date := now.Format("01-02-2006")
			key := "databases/postgres/" + env + "/" + date + "/" + datname + ".zip"
			filePath := "/tmp/" + datname + ".zip"
			uploaderr := UploadFile(sess, filePath, bucket, key)
			if uploaderr != nil {
				log.Println("Failed to upload file: ", key)
			}
		}

	}
}
