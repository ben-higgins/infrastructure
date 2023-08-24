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

                # If GITHUB_BRANCH_NAME override isn't provided in Jenkins Job then checkout to the gittag provided in repo
                if [ -z ${pipelineParams.GITHUB_BRANCH_NAME} ]
                then
                    cd ./devops-infrastructure
                    GIT_TAG=\$(python -u ./bin/get-operator-gittag.py --envName ${ENVIRONMENT} --branchName ${BRANCH_NAME} 2>&1)
                    echo "Read GIT_TAG is \${GIT_TAG}"

                    cd ${env.WORKSPACE}
                    git fetch --all --tags
                    git checkout \${GIT_TAG}

                    echo "Service Repo: git current branch name after \${GIT_TAG} checkout is: `git rev-parse --abbrev-ref HEAD`"
                    echo "Service Repo: git current commit hash after \${GIT_TAG} checkout is: `git rev-parse --short HEAD`"

                else
                    cd ${env.WORKSPACE}
                    git fetch --all --tags
                    git checkout ${pipelineParams.BRANCH_NAME}

                    echo "Service Repo: git current branch name after ${pipelineParams.BRANCH_NAME} checkout is: `git rev-parse --abbrev-ref HEAD`"
                    echo "Service Repo: git current commit hash after ${pipelineParams.BRANCH_NAME} checkout is: `git rev-parse --short HEAD`"
                fi

                cd ${env.WORKSPACE}
                cd ./devops-infrastructure

                touch ./kubeconfig.cfg
                chmod 600 ./kubeconfig.cfg

                export KUBECONFIG=./kubeconfig.cfg
                python3.7 -m venv ./
                source ./bin/activate

                pip install --upgrade pip
                pip install -r ./bin/requirements.txt

                echo "Infra Repo: git current branch name before infra tagged checkout is: `git rev-parse --abbrev-ref HEAD`"
                echo "Infra Repo: git current commit hash before infra tagged checkout is: `git rev-parse --short HEAD`"

                python -u ./bin/git-checkout.py \
                    --envName ${pipelineParams.ENVIRONMENT} \
                    --gitBranch ${pipelineParams.LIBRARY_BRANCH}

                echo "Infra Repo: git current branch name after infra tagged checkout is: `git rev-parse --abbrev-ref HEAD`"
                echo "Infra Repo: git current commit hash after infra tagged checkout is: `git rev-parse --short HEAD`"
                """
            }
        }
    }
}
