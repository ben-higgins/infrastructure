FROM ubuntu

RUN apt update -y
RUN apt install sshpass python-pip -y
RUN pip install pysftp boto3

COPY transfer.py /transfer.py
COPY known_hosts /root/.ssh/known_hosts

ENTRYPOINT /transfer.py