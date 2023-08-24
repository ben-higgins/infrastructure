#!/usr/bin/env groovy

def call(Map pipelineParams) {
    pipeline {

        stage('Deploy') {

            script {
                print(pipelineParams)

                sh """
                #!/usr/bin/env bash
                set -ex

                export KUBECONFIG=./kubeconfig.cfg

                cd ./devops-infrastructure
                source ./bin/activate

                python -u ./bin/operator-deployer.py \
                    --action ${pipelineParams.ACTION} \
                    --jobName ${pipelineParams.APP_NAME} \
                    --deployRegion ${pipelineParams.DEPLOY_REGION} \
                    --buildNumber ${pipelineParams.BUILD_NUMBER} \
                    --environment ${pipelineParams.ENVIRONMENT} \
                    --branchName ${pipelineParams.BRANCH_NAME}
                """
            }
        }
    }
}
