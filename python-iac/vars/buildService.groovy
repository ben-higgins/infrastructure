#!/usr/bin/env groovy

def call(
    PRE_SETUP=true,
    ACTION='Build'
    Map pipelineParams
) {
    pipeline {
        stage('Build') {

            script {
                print("pipeline params: ${pipelineParams}")
                pipelineParams.TARGET_BRANCH = pipelineParams.BRANCH_NAME

                if (PRE_SETUP == true) {
                    echo "pre-setup"
                    preSetupInfraRepo(pipelineParams)
                }

                if (pipelineParams.containsKey('DEPLOY_SECRETS') && pipelineParams.DEPLOY_SECRETS == true) {
                    echo "Calling deploy secrets"
                    deploySecrets(pipelineParams)
                }

                deployKubernetesApp(pipelineParams)
            }
        }
    }
}

