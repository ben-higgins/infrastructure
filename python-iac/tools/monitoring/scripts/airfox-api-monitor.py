#!/usr/bin/python

import os
import requests
import boto3
from datetime import datetime
import json
import time
import subprocess
import analytics
from lib.auth import get_header

payload = 'monitoring/' + os.environ['PAYLOAD_FILE']
logLevel = os.environ['LOG_LEVEL']
apiName = os.environ['API_NAME']
regionName = os.environ['REGION_NAME']
envType = os.environ['ENV_TYPE']
pingFrequency = os.environ['PING_FREQUENCY']
analyticsUrl = os.environ['ANALYTICS_URL']

# check if logging to segment/looker
if os.environ['ANALYTICS_URL'] == '':
    print("No analytics key provide")
    analyticsLogging = 'false'
else:
    analytics.write_key = os.environ['ANALYTICS_URL']
    analyticsLogging = 'true'

# check if elasticsearch address was provide
if os.environ['ES_SERVER'] == '':
    print("No elasticsearch server")
    esLogging = 'false'
else:
    es = os.environ['ES_SERVER']
    esLogging = 'true'

# load objects
cw = boto3.client(service_name='cloudwatch',
                  region_name=regionName)

s3 = boto3.client(service_name='s3',
                  region_name='us-east-1')

# get payload file from s3 and load variables
obj = s3.get_object(Bucket='airfox-it', Key=payload)
try:
    d = json.loads(obj['Body'].read())
except:
    print("Failed to read json file from s3")
    exit(1)
else:
    apiPayload = d[apiName]['payload']
    apiHost = d[apiName]['host']
    vendor = d[apiName]['vendor']
    apiPath = d[apiName]['path']
    apiUri = d[apiName]['uri']
    apiProtocol = d[apiName]['protocol']
    apiMethod = d[apiName]['method']

if logLevel == 'debug':
    print('apiHost: ' + str(apiHost) + '\napiPath: ' + str(apiPath) + "\npayload: " + str(apiPayload))

# ping endpoints and send results
def ping_api(header):

    if logLevel == 'debug':
        print("Content-Type: text/plain\n\n")
        for key in os.environ.keys():
            print("%30s %s \n" % (key, os.environ[key]))


    url = str(apiProtocol) + "://" + str(apiHost) + str(apiPath.replace("*str*", foxId)) + str(apiUri)
    print(url)
    # disable ssl verification
    requests.packages.urllib3.disable_warnings()

    while True:
        try:
            if apiMethod == 'GET':
                r = requests.get(url=url, data=json.dumps(apiPayload),
                            headers=header, verify=False, timeout=50)
            elif apiMethod == 'POST':
                r = requests.post(url=url, data=json.dumps(apiPayload),
                                 headers=header, verify=False, timeout=50)
        except requests.exceptions.RequestException as e:
            handle_except(e)
        else:
            # have to get renew token within this loop
            if r.status_code == 401:
                print('token might have expired')
                process_response(r)
                header = get_header(vendor)
            else:
                process_response(r)
                response = requests.head(url=url, data=json.dumps(apiPayload),
                                            headers=header, verify=False, timeout=5)
                print(response.text)


        time.sleep(float(pingFrequency))


# http get responses that don't return json
def handle_except(e):
    print(e)

    if esLogging == 'true':
        send_elasticsearch(e)
    if analyticsLogging == 'true':
        send_analytics(0)
    if logLevel == 'debug':
        diag()


# process get responses based on http status codes
def process_response(r):
    if r.status_code == 200:
        send_metric(r.elapsed.total_seconds())
        if analyticsLogging == 'true':
            send_analytics(r.elapsed.total_seconds())
        if logLevel == 'debug':
            print(r.json())
            if esLogging == 'true':
                send_elasticsearch(r.json())
    else:
        print("API returned status code: " + str(r.status_code))
        print(r.text)

        if analyticsLogging == 'true':
            send_analytics(0)
        if esLogging == 'true':
            send_elasticsearch(r.json())


# send metrics to aws cloudwatch
def send_metric(elapsedTime):
    timestamp = datetime.now()
    cw.put_metric_data(
        Namespace=vendor,
        MetricData=[
            {
                'MetricName': apiName,
                'Dimensions': [
                    {
                        'Name': 'API',
                        'Value': apiHost
                    }
                ],
                'Unit': 'Count',
                'Value': elapsedTime,
                'Timestamp': str(timestamp),
                'StorageResolution': 1
            }
        ]
    )


# perform additional diagnosis on exceptions
def diag():
    print("pinging end point to confirm dns is resolving")
    process = subprocess.Popen(["ping", "-c 5", apiHost], stdout=subprocess.PIPE)
    output = process.communicate()[0].split('\n')
    print(output)


# send to elk
def send_elasticsearch(logs):
    try:
        url = 'https://' + str(es) + '/monitoring-api/log'
        doc = {
                'apiname': apiHost,
                'path': apiPath,
                'timestamp': datetime.now(),
                'message': logs.json()
              }
        r = requests.post(url=url, data=json.dumps(doc), headers={"Content-Type":"application/json"})
    except:
        print("Failed to send metrics to elasticsearch")
        print(r.json())


# send to api gateway/lambda
def send_analytics(elapsedTime):
    timestamp = datetime.now()
    doc = {
            "apiName": apiName,
            "apiHost": apiHost,
            "apiPath": apiPath,
            "vendor": vendor,
            "elapsedTime": elapsedTime,
            "timestamp": str(timestamp),
            "envType": envType
        }

    requests.post(url=analyticsUrl, data=json.dumps(doc), headers={"Content-Type": "application/json"})

print("Begin monitoring " + str(apiName) + ": " + str(apiProtocol) + "://" + str(apiHost) + str(apiPath))

header, foxId = get_header(vendor, envType)

ping_api(header)
