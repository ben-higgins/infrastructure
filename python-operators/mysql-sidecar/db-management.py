import lib.secrets_manager as secrets
import argparse
import json
import os
import mysql.connector
import boto3
import zipfile
import shutil
import stat
from subprocess import Popen, PIPE
from datetime import datetime
import lib.exec_ctl as exe
import lib.s3 as s3
import re

parser = argparse.ArgumentParser()
parser.add_argument("-a", required=True, help="RESTORE | BACKUP action options")
parser.add_argument("-e", required=True, help="environment name")
parser.add_argument("-r", required=True, help="eks deployed region")
parser.add_argument("-b", help="backup bucket", nargs="?", const=None)
parser.add_argument("-s", required=True, help="Secret name")
args = parser.parse_args()

if args.b is None:
    bucket = "reptrak-backups"
else:
    bucket = args.b

# I haven't found a way to select just user owned databases from mysql so this is a workaround
dbnames = ['codebook','audit']

# get secrets for mysql
response = json.loads(secrets.get_secret(args.e + "/" + args.s, args.r))

for key in response:
    if key == "host":
        mysqlHost = response[key].strip()
    elif key == "username":
        masterUser = response[key].strip()
    elif key == "password":
        masterPass = response[key].strip()

def exec_tsql(cursor, command):
    try:
        cursor.execute(command)
    except mysql.connector.Error as err:
        print("Failed to execute command: {}".format(err))
        exit(1)
    finally:
        print("Command executed: " + command)

def get_tables(dbName):
    try:
        cursor.execute("USE {}".format(dbName))
    except mysql.connector.Error as err:
        print("Database {} does not exists.".format(dbName))
        exit(1)
    finally:
        print("Switched to database: " + dbName)

    try:
        cursor.execute("SHOW TABLES")
    except mysql.connector.Error as err:
        print("Error: {}".format(err))
        exit(1)
    finally:
        data = cursor.fetchall()
        tableList = []
        for row in data:
            tableList.append(row[0])
        return tableList

def get_date():
    now = datetime.now()
    time = now.strftime("%H:%M:%S")
    fTime = now.strftime("%Y") + "-" + now.strftime("%m") + "-" + now.strftime("%d") + "-" + time.replace(":", "-")
    pTime = now.strftime("%Y") + "-" + now.strftime("%m") + "-" + now.strftime("%d")
    return [fTime, pTime]

if args.a == "RESTORE":

    # for envTypes that are not standard and need something to restore
    if args.e not in "develop qa main":
        envType = "develop"
    else:
        envType = args.e

    print("Restoring...")

    cnx = mysql.connector.connect(user=masterUser, password=masterPass, host=mysqlHost, ssl_disabled=True)
    cursor = cnx.cursor()

    s3 = boto3.resource('s3')
    my_bucket = s3.Bucket(bucket)

    print(my_bucket.objects.filter(Prefix="databases/mysql/" + envType))

    unsorted = []
    for file in my_bucket.objects.filter(Prefix="databases/mysql/" + envType):
        unsorted.append(file)


    backups = [obj.key for obj in sorted(unsorted, key=lambda x: x.last_modified, reverse=True)][0:2]

    print(backups)

    for b in backups:
        zippedFile = b.rsplit('/', 1)[-1]
        dbName = zippedFile.split('-')[0]
        zippedPath = '/tmp/' + zippedFile
        unzippedPath = '/tmp/' + dbName

        # create database
        exec_tsql(cursor, "CREATE DATABASE IF NOT EXISTS " + dbName)
        #remove codebook website specific user. All access should be through the master user
        #exec_tsql(cursor, "GRANT ALL ON " + dbName + ".* TO '" + dbUser + "'@'%' IDENTIFIED BY '" + dbPass + "'")
        #exec_tsql(cursor, "FLUSH PRIVILEGES")

        s3.Bucket(bucket).download_file(b, '/tmp/' + zippedFile)
        with zipfile.ZipFile(zippedPath, 'r') as zip_ref:
            zip_ref.extractall(unzippedPath)

        tableList = get_tables(dbName)
        print(tableList)

        for file in os.listdir(unzippedPath):
            # clean out owners of views or functions
            try:
                with open(unzippedPath + "/" + file, 'r', encoding="UTF-8") as f:
                    content = f.read()
                    content_new = re.sub('DEFINER=`[^`]*`@`[^`]*`', '', content, flags = re.M)
    
                f.close()
    
                output = open(unzippedPath + "/" + file, 'w')
                output.write(content_new)
                output.close()
            except Exception as e:
                print(e)


            tableName = file.split('.')[0]
            print("checking this table exists: " + tableName)
            if tableName not in tableList:
                new_line = "mysql -h " + mysqlHost + " -u " + masterUser + " --password='" + masterPass + "' --ssl-mode=DISABLED " + dbName + " < " + os.path.join(unzippedPath, file)
                with open("/tmp/" + dbName + "_restore.sh", "a") as a_file:
                    a_file.write("\n")
                    a_file.write(new_line)
            else:
                print("Table {} already exists. Skipping".format(tableName))

        if os.path.exists("/tmp/" + dbName + "_restore.sh"):
            st = os.stat("/tmp/" + dbName + "_restore.sh")
            os.chmod("/tmp/" + dbName + "_restore.sh", st.st_mode | stat.S_IEXEC)

            response = Popen(["/bin/bash", "-c", "/tmp/" + dbName + "_restore.sh"], stdout=PIPE)
            print(response.stdout.read())
        else:
            print("Nothing to restore")


        # clean-up
        if os.path.exists("/tmp/" + dbName + "_restore.sh"):
            print("Removing file /tmp/" + dbName + "_restore.sh")
            os.remove("/tmp/" + dbName + "_restore.sh")
        if os.path.exists(zippedPath):
            print("Removing file " + zippedPath)
            os.remove(zippedPath)
        if os.path.exists(unzippedPath):
            for file in os.listdir(unzippedPath):
                print("Removing file " + os.path.join(unzippedPath, file))
                os.remove(os.path.join(unzippedPath, file))
            os.rmdir(unzippedPath)

    cursor.close()
    cnx.close()

elif args.a == "BACKUP":
    # set environment
    envType = args.e

    # get list of databases
    cnx = mysql.connector.connect(user=masterUser, password=masterPass, host=mysqlHost)
    cursor = cnx.cursor()


    for dbName in dbnames:
        if not os.path.exists('/tmp/' + dbName):
            os.makedirs('/tmp/' + dbName)

        # get tables in dbName
        tablesList = get_tables(dbName)

        print(tablesList)
        for tableName in tablesList:
            dumpFile = '/tmp/' + dbName + "/" + tableName + ".sql"
            command = "mysqldump -u " + masterUser + " --password=" + masterPass + " -h " + mysqlHost + " --set-gtid-purged=OFF --default-character-set=utf8 " + dbName + " " + tableName + " --result-file " + dumpFile
            response = exe.sub_process(command)
            print(response)

        # zip folder
        shutil.make_archive('/tmp/' + dbName, 'zip', '/tmp/' + dbName)

        # upload zip to s3
        currentDate = get_date()
        response = s3.file_upload("/tmp/" + dbName + ".zip", bucket, "databases/mysql/" + args.e + "/" + currentDate[1] + "/" + dbName + "-" + currentDate[0] +  ".zip")

        # clean-up
        if os.path.exists('/tmp/' + dbName + '.zip'):
            os.remove('/tmp/' + dbName + '.zip')
        if os.path.exists('/tmp/' + dbName):
            for file in os.listdir('/tmp/' + dbName):
                os.remove(os.path.join('/tmp/' + dbName, file))
            os.rmdir('/tmp/' + dbName)

    cursor.close()
    cnx.close()





