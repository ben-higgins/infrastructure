import argparse

from lib.s3 import S3Manager

ap = argparse.ArgumentParser()
ap.add_argument("--bucket", required=True)
ap.add_argument("--region", required=True)

args = vars(ap.parse_args())

S3Manager.delete_bucket(args["region"], args["bucket"])
