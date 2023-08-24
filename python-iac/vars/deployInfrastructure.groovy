#!/usr/bin/env groovy

def call(Map pipelineParams) {
    pipeline {

        stage('Deploy') {

            script {
                print(pipelineParams)

                sh """
                #!/usr/bin/env bash
                set -ex

                touch $WORKSPACE/kubeconfig.cfg
                chmod 600 $WORKSPACE/kubeconfig.cfg

                export KUBECONFIG=$WORKSPACE/kubeconfig.cfg


                python3.7 -m venv ${WORKSPACE}
                . ${WORKSPACE}/bin/activate

                pip install --upgrade pip
                pip install -r bin/requirements.txt

                env

                if [ "${BRANCH_OVERRIDE}" != "" ]
                then
                    git checkout ${BRANCH_OVERRIDE}
                fi

                if [ "${ACTION}" == "Deploy" ]; then

                  git fetch --all --tags
                  GIT_COMMIT=\$( python -u ./bin/git-checkout.py --envName ${ENV_NAME} --gitBranch ${BRANCH_OVERRIDE} )

                  python -u ./bin/create-update-secrets.py \
                      --region None \
                      --environment ${ENV_NAME} \
                      --secrets_directory secrets_encrypted \
                      --app devops-infrastructure

                  python -u ./bin/cluster.py \
                      --action ${ACTION} \
                      --envName ${ENV_NAME} \
                      --gitHash \$GIT_COMMIT

                  python -u ./bin/eks-cluster-config.py \
                      --envName ${ENV_NAME}

                  python -u ./bin/micro-service-dependencies.py \
                      --envName ${ENV_NAME}

                elif  [ "${ACTION}" == "Delete" ]; then

                  GIT_COMMIT=\$( python -u ./bin/git-checkout.py --envName ${ENV_NAME} --gitBranch ${BRANCH_OVERRIDE} )

                  python -u ./bin/remove-micro-services.py \
                      --envName ${ENV_NAME}

                  python -u ./bin/update-termination-protection.py \
                      --envName ${ENV_NAME} \
                      --branch ${BRANCH_OVERRIDE}

                  python -u ./bin/cluster.py \
                      --action ${ACTION} \
                      --envName ${ENV_NAME} \
                      --gitHash \$GIT_COMMIT

                  python -u ./bin/delete-snapshots.py \
                      --envName ${ENV_NAME}

                  python -u ./bin/delete-secrets.py \
                      --envName ${ENV_NAME}
                fi
                """
            }
        }
    }
}
