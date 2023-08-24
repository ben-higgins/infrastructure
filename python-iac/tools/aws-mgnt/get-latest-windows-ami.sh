#!/bin/bash

# pass in region
if [ ! $1 ]; then
  echo "Requires region"
  exit 1
fi

aws ssm --region $1 \
  get-parameters-by-path \
  --path /aws/service/ami-windows-latest \
  --query "Parameters[].[Name,Value]" | grep Windows_Server-2022-English-Full-Base