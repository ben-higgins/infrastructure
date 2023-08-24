FROM golang:1.18.10


RUN apt update && apt install -y less curl jq zip postgresql-client \
    && curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" \
    && unzip awscliv2.zip \
    && ./aws/install \
    && curl -O https://s3.us-west-2.amazonaws.com/amazon-eks/1.24.9/2023-01-11/bin/linux/amd64/kubectl \
    && mv -f kubectl /usr/bin/ \
    && chmod +x /usr/bin/kubectl \
    && rm -rf ./awscliv2.zip \
    && rm -rf ./aws

RUN curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 \
    && chmod 700 get_helm.sh \
    && ./get_helm.sh \
    && rm -f ./get_helm.sh \
    && mkdir /root/.aws

RUN curl -fsSL -o sam.zip https://github.com/aws/aws-sam-cli/releases/latest/download/aws-sam-cli-linux-x86_64.zip \
    && unzip sam.zip -d sam-installation \
    && ./sam-installation/install

COPY config /root/.aws