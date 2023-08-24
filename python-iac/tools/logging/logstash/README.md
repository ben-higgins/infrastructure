

Run logstash from local project
```bash
docker run --rm -it \
    -e ENV=(develop, qa, prod)
    -e LOGZ_TOKEN=<value> \
	-v ~/settings/:/usr/share/logstash/config/ \
	docker.elastic.co/logstash/logstash:7.6.2
```

Run logstash container from ECR
```bash
docker run --rm -it \
    -e ENV=(develop, qa, prod) \
    -e LOGZ_TOKEN=<value> \
    --name logstash \
    663946581577.dkr.ecr.us-east-1.amazonaws.com/logstash:latest
```