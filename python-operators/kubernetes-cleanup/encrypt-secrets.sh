#!/bin/bash
key_arn=arn:aws:kms:us-east-1:663946581577:key/mrk-dc1b2b97d23546529a1ebfb90347267b

if [ $1 == "encrypt" ]; then
    if [ -d "secrets" ]; then
        aws-encryption-cli \
            --encrypt \
            --input secrets --recursive \
            --wrapping-keys key=$key_arn \
            --output secrets_encrypted \
            --suppress-metadata

        if [ ! $? -eq 0 ]; then
            echo "failed to encrypt the secrets"
            echo "check if you are login into aws"
            exit 1
        fi

        git add secrets_encrypted
    fi

elif [ $1 == "decrypt" ]; then
    if [ -d "secrets_encrypted" ]; then
        rm ./secrets_encrypted/.keep
        aws-encryption-cli \
            --decrypt \
            --input secrets_encrypted --recursive \
            --wrapping-keys key=$key_arn \
            --output ./secrets/ \
            --suppress-metadata || true
        touch ./secrets_encrypted/.keep
    fi
fi
