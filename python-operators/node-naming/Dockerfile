FROM python:3.9-alpine3.16

RUN pip3 install kubernetes boto3 \
    && mkdir scripts

COPY . /scripts

ENTRYPOINT ["python", "/scripts/name-node.py"]


