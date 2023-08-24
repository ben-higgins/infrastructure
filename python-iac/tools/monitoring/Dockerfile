FROM python:2.7

VOLUME /log
CMD yum install python-pip -y
RUN pip install boto3 requests elasticsearch analytics-python requests_aws4auth --user
COPY scripts /scripts

WORKDIR /scripts
ENTRYPOINT ["bash", "/scripts/entrypoint.sh"]