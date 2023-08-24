#!/usr/bin/env groovy

def call(Map pipelineParams) {
    pipeline {

        stage('Deploy') {

            script {
                print(pipelineParams)

                sh """
                    export KUBECONFIG=./kubeconfig.cfg

                    cd ./devops-infrastructure
                    source ./bin/activate

                    python -u ./bin/airflow-deploy.py \
                        --action ${pipelineParams.ACTION} \
                        --envName ${pipelineParams.ENVIRONMENT} \
                        --gitBranch ${pipelineParams.BRANCH_NAME} \
                        --kms_key_arn ${pipelineParams.KMS_KEY_ARN}
                    """
            }
        }
    }
}
