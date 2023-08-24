#!/usr/bin/env bash

if [ -z "$ACCESS_KEY_ID" ]; then
  # assumes instance role to access s3 bucket
  s3fs ri-database-engineering-automated-data-qa-data-docs /usr/share/nginx/html -o iam_role=auto
else
  # use the passed in aws access key
  echo $ACCESS_KEY_ID:$SECRET_ACCESS_KEY > /home/nginx/.passwd-s3fs
  chmod 600 /home/nginx/.passwd-s3fs

  s3fs ri-database-engineering-automated-data-qa-data-docs /usr/share/nginx/html -o passwd_file=/home/nginx/.passwd-s3fs -o nonempty
fi

/etc/init.d/nginx start &&

tail -f /var/log/nginx/access.log
