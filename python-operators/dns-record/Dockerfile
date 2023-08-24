FROM python:slim-buster

RUN apt update && apt install curl gnupg -y && apt clean

RUN curl https://baltocdn.com/helm/signing.asc | apt-key add - && \
    apt-get install apt-transport-https --yes && \
    echo "deb https://baltocdn.com/helm/stable/debian/ all main" | tee /etc/apt/sources.list.d/helm-stable-debian.list && \
    apt-get update && apt-get install helm && apt clean

RUN pip install cloudflare boto3 kubernetes~=22.6\
    && mkdir scripts

COPY . /scripts

RUN chmod +x /scripts/entrypoint.sh

ENTRYPOINT /scripts/entrypoint.sh
