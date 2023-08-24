FROM ubuntu:20.04

# fix for broken archives
#COPY sources.list /etc/apt/sources.list
#RUN apt clean && apt autoclean

# add postgres repo

RUN apt-get update \
    && apt-get install -y gnupg2 gnupg gnupg1 python3-pip unzip curl wget ca-certificates \
    && apt-get clean
RUN wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -
RUN echo "deb http://apt.postgresql.org/pub/repos/apt/ bionic-pgdg main" | tee  /etc/apt/sources.list.d/pgdg.list

RUN apt update && apt install postgresql-client-11 libpq-dev python3-dev -y && apt clean

RUN pip3 install awscli boto3 psycopg2-binary psycopg2 \
    && mkdir scripts
#RUN apt update && apt install -y python3-psycopg2

COPY . /scripts

RUN chmod +x /scripts/entrypoint.sh

ENTRYPOINT /scripts/entrypoint.sh


