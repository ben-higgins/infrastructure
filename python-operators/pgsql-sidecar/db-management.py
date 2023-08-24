from subprocess import Popen, PIPE
import lib.secrets_manager as secrets
import argparse
import json
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import lib.exec_ctl as exe
from datetime import datetime
import shutil
import os
import lib.s3 as s3
import boto3
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument("-a", required=True, help="RESTORE | BACKUP action options")
parser.add_argument("-e", required=True, help="environment name")
parser.add_argument("-r", required=True, help="eks deployed region")
parser.add_argument("-b", help="backup bucket", nargs="?", const=None)
parser.add_argument("-s", help="override aurora secrets name", nargs="?", const=None)
args = parser.parse_args()

if args.b is None:
    bucket = "reptrak-backups"
else:
    bucket = args.b
if args.s is None:
    auroraSecret = "postgres-rds"
else:
    auroraSecret = args.s

# get secrets for aurora
response = json.loads(secrets.get_secret(args.e + "/" + auroraSecret, args.r))

for key in response:
    if key == "host":
        host = response[key].strip()
    elif key == "username":
        masterUser = response[key].strip()
    elif key == "password":
        masterPass = response[key].strip()

def get_date():
    now = datetime.now()
    time = now.strftime("%H:%M:%S")
    fTime = now.strftime("%Y") + "-" + now.strftime("%m") + "-" + now.strftime("%d") + "-" + time.replace(":", "-")
    pTime = now.strftime("%Y") + "-" + now.strftime("%m") + "-" + now.strftime("%d")
    return [fTime, pTime]

conn = psycopg2.connect(host=host,
                            dbname="postgres",
                            user=masterUser,
                            password=masterPass)
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()
cur.execute('SELECT datname FROM pg_database;')

if args.a == "BACKUP":

    envType = args.e

    for row in cur.fetchall():
        if row[0] not in "postgres template0 template1 rdsadmin":
            print(row[0])
            if not os.path.exists('/tmp/' + row[0]):
                os.makedirs('/tmp/' + row[0])

            exe.sub_process("pg_dump --dbname=postgresql://" + masterUser + ":" + masterPass + "@" + host + ":5432/" + row[0] + " --file=/tmp/" + row[0] + "/" + row[0] + ".sql")

            shutil.make_archive('/tmp/' + row[0], 'zip', '/tmp/' + row[0])

            # upload zip to s3
            currentDate = get_date()
            response = s3.file_upload("/tmp/" + row[0] + ".zip", bucket, "databases/postgres/" + args.e + "/" + currentDate[1] + "/" + row[0] + "-" + currentDate[0] +  ".zip")

            # clean-up
            if os.path.exists('/tmp/' + row[0] + '.zip'):
                os.remove('/tmp/' + row[0] + '.zip')
            if os.path.exists('/tmp/' + row[0]):
                for file in os.listdir('/tmp/' + row[0]):
                    os.remove(os.path.join('/tmp/' + row[0], file))
                os.rmdir('/tmp/' + row[0])


elif args.a == "RESTORE":
    print("Restoring...")
    # for envTypes that are not standard
    if args.e not in "develop qa main":
        envType = "develop"
    else:
        envType = args.e

    # for envTypes that are not standard but we need ot restore from something
    if args.e not in "develop qa main":
        envType = "develop"
    else:
        envType = args.e

    s3 = boto3.resource('s3')
    my_bucket = s3.Bucket(bucket)

    unsorted = []
    for file in my_bucket.objects.filter(Prefix="databases/postgres/" + envType):
        unsorted.append(file)

    # if this is a new environment there will be no backups, get develop backups
    if not len(unsorted):
        for file in my_bucket.objects.filter(Prefix="databases/postgres/develop"):
            unsorted.append(file)

        # get secrets from develop
        response = json.loads(secrets.get_secret("develop/platform-filters", "eu-west-1"))
    else:
        response = json.loads(secrets.get_secret(args.e + "/platform-filters", args.r))


    for key in response:
        if key == "REDSHIFT_USER":
            username = response[key].strip()
        elif key == "REDSHIFT_PASSWORD":
            password = response[key].strip()

    # todo this logic is flawed in that we can only restore the first db. need to make it so any unique db can be restore
    backups = [obj.key for obj in sorted(unsorted, key=lambda x: x.last_modified, reverse=True)][0:1]

    for b in backups:
        zippedFile = b.rsplit('/', 1)[-1]
        dbName = zippedFile.split('-')[0]
        zippedPath = '/tmp/' + zippedFile
        unzippedPath = '/tmp/' + dbName

        s3.Bucket(bucket).download_file(b, '/tmp/' + zippedFile)
        with zipfile.ZipFile(zippedPath, 'r') as zip_ref:
            zip_ref.extractall(unzippedPath)

        # only restore if db doesn't exist
        for row in cur.fetchall():
            if dbName == row[0]:
                print("Database already exists, aborting restore")
                exit(0)

        cur.execute("CREATE DATABASE " + dbName)

        try:
            print("Creating role user")
            cur.execute("CREATE ROLE " + username.replace("'", "") + " LOGIN PASSWORD '" + password.replace("'", "") + "'")
        except Exception as e:
            print(e)

        exe.sub_process("psql --dbname=postgresql://" + masterUser + ":" + masterPass + "@" + host + ":5432/" + dbName + " --file=/tmp/" + dbName + "/" + dbName + ".sql")

        print("Restore of db " + dbName + " completed")
        # clean-up
        if os.path.exists("/tmp/" + dbName + "_restore.sh"):
            os.remove("/tmp/" + dbName + "_restore.sh")
        if os.path.exists(zippedPath):
            os.remove(zippedPath)
        if os.path.exists(unzippedPath):
            for file in os.listdir(unzippedPath):
                os.remove(os.path.join(unzippedPath, file))
            os.rmdir(unzippedPath)


cur.close()
conn.close()
