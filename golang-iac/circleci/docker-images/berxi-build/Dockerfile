FROM alpine:3.11

ENV PACKAGES "groff less bash python3 jq curl make ca-certificates git openssh"
ENV BUILD_DEPS "gcc python3-dev linux-headers musl-dev"

RUN apk --no-cache update \
    && apk --no-cache add $PACKAGES \
    && apk add --no-cache --virtual .build-deps $BUILD_DEPS \
    && pip3 install --upgrade pip \
    && pip3 --no-cache-dir install awscli aws-sam-cli \ 
    && apk add --update npm \
    && npm install newman --global 

RUN apk del .build-deps \
	&& rm -rf /var/cache/apk/*

ADD ./config /data/config
ENV AWS_CONFIG_FILE=/data/config

# adding github.com's public ssh key to known hosts so we don't get prompted to add it to known_hosts when running git commands in circleci script
RUN mkdir /root/.ssh \
    && echo "github.com ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEAq2A7hRGmdnm9tUDbO9IDSwBK6TbQa+PXYPCPy6rbTrTtw7PHkccKrpp0yVhp5HdEIcKr6pLlVDBfOLX9QUsyCOV0wzfjIJNlGEYsdlLJizHhbn2mUjvSAHQqZETYP81eFzLQNnPHt4EVVUh7VfDESU84KezmD5QlWpXLmvU31/yMf+Se8xhHTvKSCZIFImWwoG6mbUoWf9nzpIoaSjB+weqqUUmpaaasXVal72J+UX2B+2RPW3RcT0eOzQgqlJL3RKrTJvdsjE3JEAvGq3lGHSZXy28G3skua2SmVi/w4yCE6gbODqnTWlg7+wC604ydGXA8VJiS5ap43JXiUFFAaQ==" \
        >> /root/.ssh/known_hosts

WORKDIR /data
