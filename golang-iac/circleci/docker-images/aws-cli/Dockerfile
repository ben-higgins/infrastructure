FROM alpine:3.9

ENV AWS_CLI_VERSION 1.16.122

RUN apk --no-cache update && \
    apk --no-cache add python py-pip py-setuptools ca-certificates groff less zip bash jq && \
    pip --no-cache-dir install awscli==${AWS_CLI_VERSION} && \
    rm -rf /var/cache/apk/*

ADD ./config /data/config
ENV AWS_CONFIG_FILE=/data/config

WORKDIR /data