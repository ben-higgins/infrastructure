import aws_encryption_sdk


class EncryptionManager:
    client = aws_encryption_sdk.EncryptionSDKClient()

    @classmethod
    def decrypt_file(cls, path: str, keys_arn: list) -> str:

        kms_key_provider = aws_encryption_sdk.StrictAwsKmsMasterKeyProvider(key_ids=keys_arn)

        with open(path, "rb") as file:
            file_content = file.read()
            response = cls.client.decrypt(
                source=file_content,
                key_provider=kms_key_provider,
            )
            if len(response):
                response = response[0].decode()

        return response
