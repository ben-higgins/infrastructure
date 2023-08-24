FROM python:slim-buster

RUN pip install boto3 botocore \
    && mkdir scripts

COPY . /scripts

RUN chmod +x /scripts/entrypoint.sh

ENTRYPOINT /scripts/entrypoint.sh
