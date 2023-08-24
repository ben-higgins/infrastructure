#!/usr/bin/env groovy

def call(
    PRE_SETUP=true,
    Map pipelineParams
) {
    pipeline {
        stage('Deploy') {

            script {
                print("printing pipeline params: ${pipelineParams}")
                pipelineParams.TARGET_BRANCH = pipelineParams.BRANCH_NAME

                if (pipelineParams.containsKey('LIBRARY_BRANCH') == false) {
                    pipelineParams.LIBRARY_BRANCH = 'master'
                }

                echo "LIBRARY_BRANCH is: ${pipelineParams.LIBRARY_BRANCH}"

                if (PRE_SETUP == true) {
                    echo "Operator pre-setup"
                    operatorPreSetupInfraRepo(pipelineParams)
                }

                if (pipelineParams.containsKey('DEPLOY_SECRETS') && pipelineParams.DEPLOY_SECRETS == true) {
                    echo "Calling deploy secrets"

                    deploySecrets(pipelineParams)
                }

                deployOperatorApp(pipelineParams)

            }
        }
    }
}

