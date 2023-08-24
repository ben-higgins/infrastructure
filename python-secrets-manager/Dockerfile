FROM python:slim-buster
COPY . /scripts
RUN pip install -r /scripts/requirements.txt
WORKDIR /scripts
VOLUME /scripts/secrets_encrypted
ENTRYPOINT /scripts/entrypoint.sh

