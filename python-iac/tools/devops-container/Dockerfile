FROM ubuntu:20.10

# add postgres repo
RUN apt update && apt install curl wget ca-certificates gnupg -y && apt clean
RUN wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -
RUN echo "deb http://apt.postgresql.org/pub/repos/apt/ bionic-pgdg main" | tee  /etc/apt/sources.list.d/pgdg.list

RUN apt update && apt install postgresql-client-11 \
        libpq-dev python3-dev python3-pip mysql-client unzip gnupg -y \
        && pip install awscli boto3 mysql-connector-python \
        && apt clean

RUN wget -qO - https://www.mongodb.org/static/pgp/server-5.0.asc | apt-key add - \
    && echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/5.0 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-5.0.list \
    && apt-get update \
    && apt-get install -y mongocli

