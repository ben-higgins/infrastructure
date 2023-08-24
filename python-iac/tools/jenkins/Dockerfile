FROM jenkins/jenkins:2.249.3-lts-jdk11
ENV PATH=$HOME/.gloo/bin:$PATH
USER root
RUN apt update -y \
    && apt install python-pip jq -y \
    && pip install awscli boto3 \
    && curl https://amazon-eks.s3-us-west-2.amazonaws.com/1.14.6/2019-08-22/bin/linux/amd64/kubectl -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl \
    && apt remove cmdtest -y \
    && curl -sS https://dl.yarnpkg.com/debian/pubkey.gpg | sudo apt-key add - \
    && echo "deb https://dl.yarnpkg.com/debian/ stable main" | sudo tee /etc/apt/sources.list.d/yarn.list \
    && apt update \
    && apt install yarn -y

RUN curl -sL https://run.solo.io/gloo/install | sh
RUN curl -o helm.tar.gz https://get.helm.sh/helm-v2.16.9-linux-amd64.tar.gz \
    && tar -zvxf helm.tar.gz \
    && cp cp linux-amd64/helm /usr/local/bin/helm \
    && chmod +x /usr/local/bin/helm \
    && rm -rf linux-amd64 helm.tar.gz

# install docker into docker
RUN apt-get update \
    && apt-get -y install \
            apt-transport-https \
            ca-certificates \
            gnupg2 \
            software-properties-common \
            && curl -fsSL https://download.docker.com/linux/$(. /etc/os-release; echo "$ID")/gpg > /tmp/dkey; apt-key add /tmp/dkey \
            && add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/$(. /etc/os-release; echo "$ID") $(lsb_release -cs) stable" \
            && apt-get update \
            && apt-get -y install docker-ce \
            && usermod -a -G docker jenkins

COPY id_rsa /root/.ssh/
RUN chmod 400 /root/.ssh/id_rsa