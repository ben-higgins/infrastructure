package ec2

import (
	"context"
	"log"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/ec2"
	"github.com/aws/aws-sdk-go-v2/service/ec2/types"
)

// source https://pkg.go.dev/github.com/aws/aws-sdk-go-v2/service/ec2#Client.CreateTags
func CreateTags(cfg aws.Config, resource, tagKey, tagValue string) {
	srv := ec2.NewFromConfig(cfg)

	tags := types.Tag{
		Key:   aws.String(tagKey),
		Value: aws.String(tagValue),
	}
	input := &ec2.CreateTagsInput{
		Resources: []string{resource},
		Tags:      []types.Tag{tags},
	}
	_, err := srv.CreateTags(context.TODO(), input)
	if err != nil {
		log.Printf("Error creating tags on subnets: %v", err)
	} else {
		log.Printf("Tags created on %v - [%v: %v]", resource, tagKey, tagValue)
	}
}
