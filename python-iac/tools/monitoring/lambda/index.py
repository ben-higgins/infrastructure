import json, psycopg2, boto3, base64

session = boto3.session.Session()
client = session.client(
    service_name='secretsmanager',
    region_name='us-east-1')

def get_secret(secret_name):
    get_secret_value_response = client.get_secret_value(
        SecretId=secret_name
    )
    secret = get_secret_value_response['SecretString']
    return secret


secretStr = get_secret("prod/analytics_database")
r = json.loads(secretStr)

conn = psycopg2.connect(host=r['proxy-host'], database=r['database'], user=r['user'], password=r['password'], port=r['proxy-port'])
cursor = conn.cursor()

def handler(event,context):
    e = event['body']
    r = json.loads(e)
    cursor.callproc('active_monitoring.insert_api_metrics',
                    [
                        r['apiName'],
                        r['apiHost'],
                        r['apiPath'],
                        r['vendor'],
                        r['elapsedTime'],
                        r['timestamp'],
                        r['envType']
                    ]
                    )
    conn.commit()
    return {
        'body': 'insert completed',
        'headers': {
            'Content-Type': 'text/plain'
        },
        'statusCode': 200
    }


