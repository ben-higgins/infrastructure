FROM bhspecialty/devops-builder:1.0
######
# expects env:
#   ACTION      - required
#   ENV         - required
#   REGION      - required
#   BUCKET      - optional: defaults to berxi-platform-backups-us-east-2
#   LOCALDEV    - optional: defaults to false
######

COPY ./postgres-sidecar/src /src
RUN chmod +x /src/entrypoint.sh
WORKDIR /src

ENTRYPOINT [ "./entrypoint.sh" ]
