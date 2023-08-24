FROM python:slim-buster

RUN pip install kubernetes~=22.6 slack_sdk boto3 \
    && mkdir scripts

COPY . /scripts

RUN chmod +x /scripts/entrypoint.sh

ENTRYPOINT /scripts/entrypoint.sh
