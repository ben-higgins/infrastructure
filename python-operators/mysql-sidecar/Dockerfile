FROM ubuntu:20.10

# fix for broken archives
COPY sources.list /etc/apt/sources.list
RUN apt clean && apt autoclean

RUN apt update \
    && apt install python3-pip mysql-client unzip -y \
    && pip install awscli boto3 \
    && pip install mysql-connector-python \
    && apt clean \
    && mkdir scripts

COPY . /scripts

RUN chmod +x /scripts/entrypoint.sh

ENTRYPOINT /scripts/entrypoint.sh


