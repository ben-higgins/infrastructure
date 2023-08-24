FROM python:3.8.16

ENV GOROOT=/usr/local/go
ENV GOPATH=$HOME/go
ENV PATH=$GOPATH/bin:$GOROOT/bin:$PATH

COPY ./requirements.txt /
RUN apt update && apt install less curl postgresql-client jq zip -y

RUN pip install -r /requirements.txt \
    && curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" \
    &&  unzip awscliv2.zip \
    && ./aws/install \
    && curl -O https://s3.us-west-2.amazonaws.com/amazon-eks/1.24.9/2023-01-11/bin/linux/amd64/kubectl \
    && mv -f kubectl /usr/bin/ \
    && chmod +x /usr/bin/kubectl

RUN curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 \
    && chmod 700 get_helm.sh \
    && ./get_helm.sh

RUN curl -fsSL -o go.tar.gz https://go.dev/dl/go1.18.10.linux-amd64.tar.gz \
    && tar -C /usr/local -xzf go.tar.gz