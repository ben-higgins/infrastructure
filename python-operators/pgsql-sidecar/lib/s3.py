import boto3
from botocore.exceptions import ClientError

def file_upload(file_name, bucket, object_name=None):
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
    s3_client = boto3.client('s3', region_name='us-east-1')
    try:
        response = s3_client.upload_file(file_name, bucket, object_name)
    except ClientError as e:
        logging.error(e)
        return False
    return True


def sync_s3(bucket, envName, prefix):
    # for nested stacks, the sub stack is called by url to an template in s3
    for filename in os.listdir("./cfn"):
        file_upload("./cfn/" + filename, bucket, envName + "/" + prefix + "/" + filename)

def file_download(bucket, count, region):
    s3 = boto3.client('s3', region_name=region)
    response = s3.list_objects_v2(
        Bucket=bucket,
        MaxKeys=count,
        Prefix='dev'
    )
    return response