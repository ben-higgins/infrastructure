
Sisense Logging paths:

https://support.sisense.com/hc/en-us/articles/230651328-Sisense-Data-Files-and-Logs

```bash
docker run -d \
  --name=filebeat \
  --user=root \
  --volume="$(pwd)/sisense.filebeat.yml:/usr/share/filebeat/filebeat.yml:ro" \
  --volume="c:\ProgramData\Sisense:/sisense-logs:ro" \
  -e -strict.perms=false \
  -e LOGSTASH_HOST=localhost \
  -e LOGSTASH_PORT=5044 \
  docker.elastic.co/beats/filebeat:7.6.2 
```