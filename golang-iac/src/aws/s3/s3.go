package s3

import (
	"bytes"
	"context"
	"log"
	"os"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/s3/types"
)

// source https://github.com/aws/aws-sdk-go-v2/blob/main/service/s3/api_op_CreateBucket.go
func CreateBucket(cfg aws.Config, bucketName, region string) {
	// create the s3 client
	svc := s3.NewFromConfig(cfg)

	_, err := svc.CreateBucket(context.TODO(), &s3.CreateBucketInput{
		Bucket: aws.String(bucketName),
		CreateBucketConfiguration: &types.CreateBucketConfiguration{
			LocationConstraint: types.BucketLocationConstraint(region),
		},
	})
	if err != nil {
		log.Println(err)
	} else {
		log.Println("New S3 bucket created")
	}
}

// source https://github.com/aws/aws-sdk-go-v2/blob/main/service/s3/api_op_DeleteBucket.go
func DeleteBucket(cfg aws.Config, bucketName string) {
	// create the s3 client
	svc := s3.NewFromConfig(cfg)

	// get a list of objects to delete so that bucket can be removed
	result, err := svc.ListObjectsV2(context.TODO(), &s3.ListObjectsV2Input{
		Bucket: aws.String(bucketName),
	})

	//var contents []types.Object
	if err != nil {
		log.Printf("Couldn't list objects in bucket %v. Here's why: %v\n", bucketName, err)
	} else {
		var objectIds []types.ObjectIdentifier
		for _, i := range result.Contents {
			objectIds = append(objectIds, types.ObjectIdentifier{Key: aws.String(*i.Key)})
		}

		_, err := svc.DeleteObjects(context.TODO(), &s3.DeleteObjectsInput{
			Bucket: aws.String(bucketName),
			Delete: &types.Delete{Objects: objectIds},
		})
		if err != nil {
			log.Printf("Couldn't delete objects from bucket %v. Here's why: %v\n", bucketName, err)
		}

	}

	_, err = svc.DeleteBucket(context.TODO(), &s3.DeleteBucketInput{
		Bucket: aws.String(bucketName),
	})
	if err != nil {
		log.Println("Unable to delete bucket %q, %v", bucketName, err)
	} else {
		log.Println("Bucket deleted")
	}

}

// source https://github.com/aws/aws-sdk-go-v2/blob/main/service/s3/api_op_PutObject.go
func S3PutObject(cfg aws.Config, bucketName, key, path, fileName string) error {
	svc := s3.NewFromConfig(cfg)

	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()

	_, err = svc.PutObject(context.TODO(),
		&s3.PutObjectInput{
			Bucket: aws.String(bucketName),
			Key:    aws.String(key + "/" + fileName),
			Body:   f,
		},
	)
	if err != nil {
		return err
	}

	return nil

}

// source https://pkg.go.dev/github.com/aws/aws-sdk-go-v2/service/s3#Client.GetObject
func S3GetObject(cfg aws.Config, bucketName, path string) (string, error) {
	svc := s3.NewFromConfig(cfg)
	result, err := svc.GetObject(context.TODO(), &s3.GetObjectInput{
		Bucket: aws.String(bucketName),
		Key:    aws.String(path),
	})

	buf := new(bytes.Buffer)
	buf.ReadFrom(result.Body)
	fileContent := buf.Bytes()
	fileName := path[strings.LastIndex(path, "/")+1:]

	f, err := os.Create("/tmp/" + fileName)
	if err != nil {
		log.Println("Failed to create file: ", err)
	}
	_, err = f.Write(fileContent)

	return "/tmp/" + fileName, err
}

func ListS3Objects(cfg aws.Config, bucketName, path string) ([]types.Object, error) {
	svc := s3.NewFromConfig(cfg)
	result, err := svc.ListObjectsV2(context.TODO(), &s3.ListObjectsV2Input{
		Bucket: aws.String(bucketName),
		Prefix: aws.String(path),
	})

	var contents []types.Object
	if err != nil {
		log.Printf("Couldn't list objects in bucket %v: %v\n", bucketName, err)
	} else {
		contents = result.Contents
	}
	return contents, err
}
