FROM python:3.9-alpine3.16

RUN pip3 install kubernetes \
    && mkdir scripts

COPY . /scripts

ENTRYPOINT ["python", "/scripts/replica-manager.py"]


