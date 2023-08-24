import base64
import json
import warnings
from typing import Any, AnyStr, Callable, Dict, List, Optional, Union

import boto3
import yaml
from botocore.exceptions import ClientError
from cryptography.fernet import Fernet

from .cloudformation_manager import CloudformationManager
from .kms import NUM_BYTES_FOR_LEN
from .logger import logging


class SecretManager:
    __client = {}

    @classmethod
    def __get_client(cls, region) -> boto3.session.Session.client:
        if region not in cls.__client:
            cls.__client[region] = boto3.client("secretsmanager", region_name=region)
        return cls.__client[region]

    @classmethod
    def get_secret(
        cls, region: str, secret_name: str, json_decode: bool = False
    ) -> Union[Dict[str, Any], AnyStr, int, float, bool, List[Any]]:
        client = cls.__get_client(region)

        print(
            "\nAttempting to fetch secret value for:"
            f"{secret_name} in region: {region}\n"
        )
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)

        secret = None

        if "SecretString" in get_secret_value_response:
            secret = get_secret_value_response["SecretString"]
        elif "SecretBinary" in get_secret_value_response:
            secret = base64.b64decode(get_secret_value_response["SecretBinary"])

        if not secret:
            raise Exception(f'Error getting secret "{secret_name}" in region "{region}"')

        if json_decode:
            secret = json.loads(secret)

        return secret

    @classmethod
    def get_secrets(
        cls, region, filters: Optional[List[Dict[str, str]]] = None, order: str = "desc", max_results: int = 10000
    ) -> Dict[str, List[Dict[str, List[AnyStr]]]]:
        client = cls.__get_client(region)
        paginator = client.get_paginator("list_secrets")

        pages = paginator.paginate(PaginationConfig={"MaxItems": max_results}, Filters=filters or [], SortOrder=order)

        return {"SecretList": [page for page in pages]}

    @classmethod
    def create_secret(
        cls, region: str, secret_name: str, secret_string: str, secret_desc: Optional[str] = None
    ) -> bool:
        client = cls.__get_client(region)
        try:
            logging.info(f"Creating secret {secret_name} in region {region}")
            create_secret_response = client.create_secret(
                Name=secret_name, Description=secret_desc, SecretString=secret_string
            )
            logging.info(f'Secret create success: {create_secret_response["ARN"]}')
        except ClientError as e:
            logging.error(f'Client error: {e.response["Error"]["Code"]} : {e}')
            if e.response["Error"]["Code"] == "ResourceExistsException":
                logging.info("Secret already exists, syncing")
                return cls.update_secret(region, secret_name, secret_string, secret_desc)

            raise e

        except Exception as e:
            logging.error(f"General error creating secret: {e}")
            raise e

        return True

    @classmethod
    def update_secret(cls, region: str, secret_name: str, secret_string: str, secret_desc: Optional[str]) -> bool:
        client = cls.__get_client(region)
        try:
            logging.info(f"Updating secret: {secret_name}")
            client.update_secret(SecretId=secret_name, Description=secret_desc, SecretString=secret_string)
            logging.info("Secret update success")
        except ClientError as e:
            logging.error(f'Client error: {e.response["Error"]["Code"]} : {e}')
            raise e
        except Exception as e:
            logging.error(f"General error updating secret: {e}")
            raise e

        return True

    @classmethod
    def get_secret_description(cls, region, secret_name) -> Dict[str, Any]:
        client = cls.__get_client(region)
        try:
            return client.describe_secret(SecretId=secret_name)
        except ClientError as e:
            logging.error(f'Client error: {e.response["Error"]["Code"]} : {e}')
            raise e
        except Exception as e:
            logging.error(f"General error getting secrets {secret_name}: {e}")
            raise e

    @classmethod
    def delete_secret(cls, region: str, secret_name: str, force_delete_without_recovery: bool = True, raise_on_error: bool = True):
        client = cls.__get_client(region)
        try:
            logging.info("Deleting secret: " + secret_name)
            client.delete_secret(SecretId=secret_name, ForceDeleteWithoutRecovery=force_delete_without_recovery)
            logging.info("Deleted successfully")
        except ClientError as e:
            logging.error(f'Client error: {e.response["Error"]["Code"]} : {e}')
            if raise_on_error:
                raise e
            return False
        except Exception as e:
            logging.error(f"General error: {e}")
            if raise_on_error:
                raise e
            return False

        return True


class ServiceSecretManager(SecretManager):
    SERVICES = {
        "mysql": "MYSQL_",
        "mongodb": "MONGO_",
        "redis": "REDIS_",
        "pgsql": "PGSQL_",
    }

    @classmethod
    def provision_helm(cls, helm: AnyStr, environment: str, region: str):
        secrets = {}
        helm_map = yaml.load(helm, Loader=yaml.FullLoader)

        for key in helm_map.keys():
            _service_name = key.lower()
            if _service_name not in cls.SERVICES.keys():
                continue

            if helm_map[key] is not True:
                continue

            logging.info(f"Getting {key} secrets")
            secrets = {**secrets, **cls.fetch_infra_service_secret(_service_name, environment, region)}

        if len(secrets.keys()) == 0:
            logging.warning("No services defined in HELM were found to be provisioned")

        return secrets

    @classmethod
    def dict_to_dotenv_lines(cls, obj: dict, prefix: Optional[str] = None) -> str:
        dotenv_lines = ""
        for key in obj:
            env_key = f"{prefix}{key.upper()}" if prefix else key.upper()
            dotenv_lines = dotenv_lines + f"{env_key}={str(obj[key])}\n"

        return dotenv_lines

    @classmethod
    def fetch_infra_service_secret(cls, service_name: str, environment: str, region: str):
        if service_name == "mongodb":
            return cls._fetch_mongo_secret(environment, region)
        if service_name == "redis":
            return cls._fetch_redis_secrets(environment, region)
        if service_name == "mysql":
            return cls._fetch_mysql_secret(environment, region)
        if service_name == "pgsql":
            return cls._fetch_pgsql_secret(environment, region)

        return {}

    @classmethod
    def prefix_secrets(cls, secrets: Dict[str, Any], prefix: str, loop_callback: Optional[Callable] = None):
        prefixed = {}
        for key in secrets:
            prefixed[f"{prefix}{key.upper()}"] = secrets[key]
            if loop_callback:
                loop_callback(prefixed, key, secrets[key], prefix)

        return prefixed

    @classmethod
    def fetch_secret_available_in_list(cls, secrets_list: List[str], environment: str, region: str):
        for secret_key_index, secret_key in enumerate(secrets_list):
            try:
                return cls.get_secret(region, f"{environment}/{secret_key}", json_decode=True)
            except Exception as e:
                logging.error(
                    f'Error fetching secret key "{environment}/{secret_key}" in region {region} [[{secret_key_index}]{e}]'
                )

        logging.error(f'Error fetching secret keys "{environment}/{secrets_list}" in region {region}')
        return {}

    @classmethod
    def _fix_credentials_keys(
        cls, secrets_prefixed: Dict[str, Any], key: str, value: Any, prefix: Optional[str] = None
    ):
        if key == "username":
            secrets_prefixed[f"{prefix}USER"] = value

    @classmethod
    def _fetch_redis_secrets(cls, environment: str, region: str) -> dict:
        stack_name = CloudformationManager.get_service_stack_name(region, environment, "Elasticache")
        outputs = CloudformationManager.get_stack_outputs(region, stack_name)

        secrets = {}
        for output in outputs:
            if output["OutputKey"] == "RedisEndpoint":
                secrets["HOST"] = output["OutputValue"]
            elif output["OutputKey"] == "RedisEndpointPort":
                secrets["PORT"] = output["OutputValue"]

        return cls.prefix_secrets(secrets, cls.SERVICES["redis"])

    @classmethod
    def _fetch_mongo_secret(cls, environment: str, region: str):
        secrets = cls.fetch_secret_available_in_list(["documentdb-cluster"], environment, region)

        return cls.prefix_secrets(secrets, cls.SERVICES["mongodb"])

    @classmethod
    def _fetch_mysql_secret(cls, environment: str, region: str):
        secrets = cls.fetch_secret_available_in_list(["mysql-rds", "aurora-mysql-cluster"], environment, region)

        return cls.prefix_secrets(secrets, cls.SERVICES["mysql"], cls._fix_credentials_keys)

    @classmethod
    def _fetch_pgsql_secret(cls, environment: str, region: str):
        secrets = cls.fetch_secret_available_in_list(["postgres-rds", "aurora-postgresql-cluster"], environment, region)

        return cls.prefix_secrets(secrets, cls.SERVICES["pgsql"], cls._fix_credentials_keys)


def get_secret(secret_name, region):
    warnings.warn(
        f"get_secret is deprecated, use {SecretManager.__module__}.SecretManager.get_secret instead", DeprecationWarning
    )
    return SecretManager.get_secret(region, secret_name)


def get_secrets_by_filters(filters, region, order="desc", max_results=10000):
    warnings.warn(
        f"get_secret is deprecated, use {SecretManager.__module__}.SecretManager.get_secrets instead",
        DeprecationWarning,
    )
    return SecretManager.get_secrets(region, filters=filters, order=order, max_results=max_results)


def get_all_secrets(region, filters=None):
    warnings.warn(
        f"get_secret is deprecated, use {SecretManager.__module__}.SecretManager.get_secrets instead",
        DeprecationWarning,
    )
    return SecretManager.get_secrets(region, filters=filters, max_results=10000)["SecretList"]


def create_secret(secretName, secretString, secretDesc, region):
    warnings.warn(
        f"get_secret is deprecated, use {SecretManager.__module__}.SecretManager.create_secret instead",
        DeprecationWarning,
    )
    return SecretManager.create_secret(region, secretName, secretString, secretDesc)


def get_secret_description(secretName, region):
    warnings.warn(
        f"get_secret is deprecated, use {SecretManager.__module__}.SecretManager.get_secret_description instead",
        DeprecationWarning,
    )
    try:
        return SecretManager.get_secret_description(region, secretName)["Description"]
    except Exception as e:
        logging.error(e)
        return "Secrets for " + secretName


def get_json_secret_value(secretName, region):
    warnings.warn(
        f"get_secret is deprecated, use {SecretManager.__module__}.SecretManager.get_secret instead", DeprecationWarning
    )
    return SecretManager.get_secret(region, secretName, json_decode=True)


def delete_secret(secretName, region):
    warnings.warn(
        f"get_secret is deprecated, use {SecretManager.__module__}.SecretManager.delete_secret instead",
        DeprecationWarning,
    )
    return SecretManager.delete_secret(region, secretName)


def describe_secret(secretName, region):
    warnings.warn(
        f"get_secret is deprecated, use {SecretManager.__module__}.SecretManager.get_secret_description instead",
        DeprecationWarning,
    )
    return SecretManager.get_secret_description(region, secretName)


def create_data_key(cmk_id, key_spec="AES_256"):
    """Generate a data key to use when encrypting and decrypting data

    :param cmk_id: KMS CMK ID or ARN under which to generate and encrypt the
    data key.
    :param key_spec: Length of the data encryption key. Supported values:
        'AES_128': Generate a 128-bit symmetric key
        'AES_256': Generate a 256-bit symmetric key
    :return Tuple(EncryptedDataKey, PlaintextDataKey) where:
        EncryptedDataKey: Encrypted CiphertextBlob data key as binary string
        PlaintextDataKey: Plaintext base64-encoded data key as binary string
    :return Tuple(None, None) if error
    """

    # Create data key
    kms_client = boto3.client("kms")
    try:
        response = kms_client.generate_data_key(KeyId=cmk_id, KeySpec=key_spec)
    except ClientError as e:
        print(e)
        return None, None

    # Return the encrypted and plaintext data key
    return response["CiphertextBlob"], base64.b64encode(response["Plaintext"])


def retrieve_cmk(desc):
    """Retrieve an existing KMS CMK based on its description

    :param desc: Description of CMK specified when the CMK was created
    :return Tuple(KeyId, KeyArn) where:
        KeyId: CMK ID
        KeyArn: Amazon Resource Name of CMK
    :return Tuple(None, None) if a CMK with the specified description was
    not found
    """

    # Retrieve a list of existing CMKs
    # If more than 100 keys exist, retrieve and process them in batches
    kms_client = boto3.client("kms")
    try:
        response = kms_client.list_keys()
    except ClientError as e:
        logging.error(e)
        return None, None

    done = False
    while not done:
        for cmk in response["Keys"]:
            # Get info about the key, including its description
            try:
                key_info = kms_client.describe_key(KeyId=cmk["KeyArn"])
            except ClientError as e:
                logging.error(e)
                return None, None

            # Is this the key we're looking for?
            if key_info["KeyMetadata"]["Description"] == desc:
                return cmk["KeyId"], cmk["KeyArn"]

        # Are there more keys to retrieve?
        if not response["Truncated"]:
            # No, the CMK was not found
            logging.debug("A CMK with the specified description was not found")
            done = True
        else:
            # Yes, retrieve another batch
            try:
                response = kms_client.list_keys(Marker=response["NextMarker"])
            except ClientError as e:
                logging.error(e)
                return None, None

    # All existing CMKs were checked and the desired key was not found
    return None, None


def encrypt_file(filename, cmk_id):
    """Encrypt a file using an AWS KMS CMK

    A data key is generated and associated with the CMK.
    The encrypted data key is saved with the encrypted file. This enables the
    file to be decrypted at any time in the future and by any program that
    has the credentials to decrypt the data key.
    The encrypted file is saved to <filename>.encrypted
    Limitation: The contents of filename must fit in memory.

    :param filename: File to encrypt
    :param cmk_id: AWS KMS CMK ID or ARN
    :return: True if file was encrypted. Otherwise, False.
    """

    # Read the entire file into memory
    try:
        with open(filename, "rb") as file:
            file_contents = file.read()
    except OSError as e:
        print(e)
        return False

    # Generate a data key associated with the CMK
    # The data key is used to encrypt the file. Each file can use its own
    # data key or data keys can be shared among files.
    # Specify either the CMK ID or ARN
    data_key_encrypted, data_key_plaintext = create_data_key(cmk_id)
    if data_key_encrypted is None:
        return False

    # Encrypt the file
    f = Fernet(data_key_plaintext)
    file_contents_encrypted = f.encrypt(file_contents)

    # Write the encrypted data key and encrypted file contents together
    try:
        with open(filename + ".encrypted", "wb") as file_encrypted:
            file_encrypted.write(len(data_key_encrypted).to_bytes(NUM_BYTES_FOR_LEN, byteorder="big"))
            file_encrypted.write(data_key_encrypted)
            file_encrypted.write(file_contents_encrypted)
    except OSError as e:
        print(e)
        return False

    return True
