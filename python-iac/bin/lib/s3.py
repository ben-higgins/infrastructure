import logging
from typing import Optional, Union

import boto3
from botocore.exceptions import ClientError

from .core_components import AwsServiceManager


class S3Manager(AwsServiceManager):
    service = "s3"

    @classmethod
    def list_bucket_objects(cls, region: str, bucket: str) -> [dict]:
        s3_client = cls.get_client(region)
        """
        List all objects for the given bucket.

        :param bucket: Bucket name.
        :return: A [dict] containing the elements in the bucket.

        Example of a single object.

        {
            'Key': 'example/example.txt',
            'LastModified': datetime.datetime(2019, 7, 4, 13, 50, 34, 893000, tzinfo=tzutc()),
            'ETag': '"b11564415be7f58435013b414a59ae5c"',
            'Size': 115280,
            'StorageClass': 'STANDARD',
            'Owner': {
                'DisplayName': 'webfile',
                'ID': '75aa57f09aa0c8caeab4f8c24e99d10f8e7faeebf76c078efc7c6caea54ba06a'
            }
        }

        """
        try:
            contents = s3_client.list_objects(Bucket=bucket)['Contents']
        except KeyError:
            # No Contents Key, empty bucket.
            return []
        else:
            return contents

    @classmethod
    def file_upload(
            cls,
            region: str,
            file_name: str,
            bucket: str,
            object_name: Optional[str],
            return_response: bool = False,
            extra_args: dict = {},
            ) -> Union[bool or dict]:
        """Upload a file to an S3 bucket

        :param file_name: File to upload
        :param bucket: Bucket to upload to
        :param object_name: S3 object name. If not specified then file_name is used
        :return: True if file was uploaded, else False
        """

        # If S3 object_name was not specified, use file_name
        if object_name is None:
            object_name = file_name

        # Upload the file. The region is hardcoded for now because there's no way to
        # create a bucket with cloudformation before uploading the files to that bucket
        s3_client = cls.get_client(region)
        try:
            response = s3_client.upload_file(file_name, bucket, object_name, ExtraArgs=extra_args)
            if return_response:
                return response
        except ClientError as e:
            logging.error(e)
            return False
        return True

    @classmethod
    def create_bucket(cls, region: str, name: str, private=True, versioning=False):
        s3_client = cls.get_client(region)
        s3_client.create_bucket(Bucket=name, CreateBucketConfiguration={"LocationConstraint": region})

        if private:
            s3_client.put_public_access_block(
                    Bucket=name,
                    PublicAccessBlockConfiguration={
                            "BlockPublicAcls":       True,
                            "IgnorePublicAcls":      True,
                            "BlockPublicPolicy":     True,
                            "RestrictPublicBuckets": True,
                            },
                    )

        if versioning:
            s3 = boto3.resource("s3", region_name=region)
            versioning = s3.BucketVersioning(name)
            versioning.enable()
        else:
            s3 = boto3.resource("s3", region_name=region)
            versioning = s3.BucketVersioning(name)
            versioning.disable()

    @classmethod
    def create_folder(cls, region, bucket_name, folder_name):
        s3_client = cls.get_client(region)
        try:
            s3_client.put_object(Bucket=bucket_name, Key=(folder_name + "/"))
        except Exception:
            pass

    @classmethod
    def delete_bucket(cls, region, bucket_name):
        s3_client = cls.get_resource(region)
        bucket = s3_client.Bucket(bucket_name)
        bucket_versioning = s3_client.BucketVersioning(bucket_name)

        if bucket_versioning.status == "Enabled":
            bucket.object_versions.delete()
        else:
            bucket.objects.all().delete()

        bucket.delete()

    @classmethod
    def check_bucket_key(cls, region: str, bucket: str, key: str, return_metadata: bool = False) -> Union[bool or dict]:
        s3_client = cls.get_client(region)
        try:
            metadata = s3_client.head_object(Bucket=bucket, Key=key)
            if return_metadata:
                return metadata
        except ClientError as e:
            logging.error(e.response["Error"])
            return int(e.response["Error"]["Code"]) != 404
        return True

    @classmethod
    def list_object_versions(cls, region: str, bucket_name: str, object_key: str, max_versions: int = 1):
        s3_client = cls.get_client(region)
        return s3_client.list_object_versions(Bucket=bucket_name, KeyMarker=object_key, MaxKeys=max_versions).get(
                "Versions"
                )

    @classmethod
    def permanently_delete_object(cls, region: str, bucket: str, object_key: str):
        s3_client = cls.get_resource(region)
        bucket = s3_client.Bucket(bucket)
        try:
            bucket.object_versions.filter(Prefix=object_key).delete()
            logging.info("Permanently deleted all versions of object %s.", object_key)
        except ClientError:
            logging.exception("Couldn't delete all versions of %s.", object_key)
            raise
