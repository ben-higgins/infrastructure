### Docker Build
```bash
docker build -t dynata-data-transfer .
```

### Docker run
The container can run outside of AWS as long as the access keys are provided as environment variables. If running in AWS, the container needs the following access in instance role policy.

1. S3 read/write to bucket 'ri-etl'
2. Read permission to Elastic Container Registry
3. Read permission to Secrets Manager

Run locally
```bash
docker run -d \
    --name dynata \
    -e AWS_ACCESS_KEY_ID=<your access key> \
    -e AWS_SECRET_ACCESS_KEY=<your secret access key> \
    663946581577.dkr.ecr.us-east-1.amazonaws.com/dynata-data-transfer:latest
```

Container will stop after completing the transfer. To run as a scheduled job:
```bash
crontab -e

30 2 * * * docker run dynata
```