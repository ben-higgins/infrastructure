#!/bin/bash

cd package

zip -r9 ../lambda_function.zip .

cd ../

zip -g lambda_function.zip index.py

aws s3 --region us-east-1 cp lambda_function.zip s3://airfox-it/monitoring/lambda_function.zip
