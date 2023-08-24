def call (Map config) {
    stage('Check out Infrastructure repo') {
            dir ('devops-infrastructure') {
                git branch: 'gittag',
                    credentialsId: 'f1bb78e1-6fd3-40e0-876b-753cf75ed889',
                    url: 'git@github.com:RepTrak/devops-infrastructure.git'
            }
        }

    stage('retrieveGitTag') {
        script {
            GIT_TAG = sh (
            script: """
                    cd ./devops-infrastructure
                    python -u ./bin/get-gittag.py \
                        --envName ${config.envName} \
                        --branchName ${config.branchName}
                    """,
            returnStdout: true
            ).trim()
            return GIT_TAG
        }
    }



}
