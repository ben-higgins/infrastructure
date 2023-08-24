#!/usr/bin/env groovy
// Expected params:
// app=pipelineParams.APP_NAME
// environment=target_branch
// region='us-east-1',
// secretsDirectory=pipelineParams.SECRETS_DIRECTORY
// kms_key_arn=pipelineParams.KMS_KEY_ARN

def call(Map pipelineParams) {
    pipeline {

        stage('Deploy') {

            script {

                sh """
                #!/usr/bin/env bash
                set -ex

                export KUBECONFIG=./kubeconfig.cfg

                cd ./devops-infrastructure
                source ./bin/activate

                python -u ./bin/create-update-secrets.py \
                    --app ${pipelineParams.APP_NAME} \
                    --branch_name ${pipelineParams.BRANCH_NAME} \
                    --environment ${pipelineParams.ENVIRONMENT} \
                    --secrets_directory ${pipelineParams.SECRETS_DIRECTORY} \
                    --region ${pipelineParams.DEPLOY_REGION} \
                    --kms_key_arn ${pipelineParams.KMS_KEY_ARN}
                """
            }
        }
    }
}
