FROM nginx
USER root
RUN rm -rf /var/lib/apt/lists/lock \
    && apt-get update \
    && apt-get install -y git build-essential libfuse-dev libcurl4-openssl-dev libxml2-dev pkg-config libssl-dev \
        mime-support \
        automake \
        libtool \
        lsb-release \
        python3 \
        python3-pip \
        python3-setuptools \
        groff \
        s3fs \
        vim

RUN sed -i 's/user  nginx/user  root/g' /etc/nginx/nginx.conf \
    && rm -rf /usr/share/nginx/html/*


WORKDIR /scripts

COPY . /scripts
RUN chmod +x /scripts/entrypoint.sh
ENTRYPOINT /scripts/entrypoint.sh