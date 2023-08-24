#!/usr/bin/env groovy

def call(Map pipelineParams) {
    pipeline {
        stage('Check out Infrastructure repo') {
            dir ('devops-infrastructure') {
                git branch: pipelineParams.LIBRARY_BRANCH,
                    credentialsId: 'f1bb78e1-6fd3-40e0-876b-753cf75ed889',
                    url: 'git@github.com:RepTrak/devops-infrastructure.git'
            }
        }

        stage('PreSetup') {

            script {

                print(pipelineParams)

                sh """
                #!/usr/bin/env bash
                set -ex
                env

                cd ${pipelineParams.PIPELINE_NAME}
                # TODO: Replace this checkout as the multi branch already handles it
                git fetch --all --tags
                git checkout ${pipelineParams.BRANCH_NAME}
                cd ${env.WORKSPACE}

                cd ./devops-infrastructure

                touch ./kubeconfig.cfg
                chmod 600 ./kubeconfig.cfg

                export KUBECONFIG=./kubeconfig.cfg
                python3.7 -m venv ./
                source ./bin/activate

                pip install --upgrade pip
                pip install -r ./bin/requirements.txt

                python -u ./bin/git-checkout.py \
                    --envName ${pipelineParams.ENVIRONMENT} \
                    --gitBranch ${pipelineParams.LIBRARY_BRANCH}

                echo "git branch is"
                git rev-parse --abbrev-ref HEAD
                """
            }
        }
    }
}
