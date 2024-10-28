def execute_commands(commands, os_name, recommended_os) {
    if("${os_name}" == "linux") {
        if("${recommended_os}" == "only_linux" || "${recommended_os}" == "all_distros") {
            sh "${commands}"
        }
    }
    if("${os_name}" == "windows") {
        if("${recommended_os}" == "only_windows" || "${recommended_os}" == "all_distros") {
            powershell "${commands}"
        }
    }
}

def delete_directory(directory, os_name) {
    execute_commands(
        """
            if [ -d "./${directory}" ]
            then
                rm -r ./${directory};
            fi
        """,
        "${os_name}",
        "only_linux"
    )
    execute_commands(
        """
            if(Test-Path -Path .\\${directory}\\) {
                Remove-Item -Force -Recurse -Path .\\${directory}\\
            }
        """,
        "${os_name}",
        "only_windows"
    )
}

def fetch_git_repository(APPLICATION_NAME, JENKINS_REPO_DIR, DATA_SOURCE_BRANCH, DATA_SOURCE_URL) {

    echo """
        Fetch ${APPLICATION_NAME}
    """

    try {

        sh """
            git config --global --add safe.directory '*';
        """

        dir("${JENKINS_REPO_DIR}") {

            git credentialsId: 'git-gitea-tbs093a',
                branch: "${DATA_SOURCE_BRANCH}",
                url: "${DATA_SOURCE_URL}"

            sh """
                ls -la
            """
        }

    } catch(error) {

        throw(error)
    }
}

def set_env_vars(JENKINS_REPO_DIR, GIT_REPO_URL, VARS) {

    echo """
        Set Env Vars
    """

    try {

        dir("${JENKINS_REPO_DIR}") {

            withCredentials(
                [
                    usernamePassword(
                        credentialsId: 'telegram-pump-bot-credentials',
                        passwordVariable: 'TELETHON_BOT_TOKEN',
                        usernameVariable: 'TELETHON_BOT_NAME'
                    ),
                    usernamePassword(
                        credentialsId: 'telegram-00x097-user-credentials',
                        passwordVariable: 'TELETHON_API_HASH',
                        usernameVariable: 'TELETHON_API_ID'
                    ),
                    usernamePassword(
                        credentialsId: 'telegram-00x097-user-info',
                        passwordVariable: 'TELETHON_API_PHONE',
                        usernameVariable: 'TELETHON_USER_ID'
                    ),
                    usernamePassword(
                        credentialsId: 'kucoin-zukkamil-api-secrets',
                        passwordVariable: 'KUCOIN_API_SECRET',
                        usernameVariable: 'KUCOIN_API_KEY'
                    ),
                    usernamePassword(
                        credentialsId: 'kucoin-zukkamil-api-credentials',
                        passwordVariable: 'KUCOIN_API_KEY_PASSPHRASE',
                        usernameVariable: 'KUCOIN_USERNAME'
                    ),
                    usernamePassword(
                        credentialsId: 'mexc-zukkamil-api-secrets',
                        passwordVariable: 'MEXC_API_SECRET',
                        usernameVariable: 'MEXC_API_KEY'
                    ),
                ]
            ) {

                GIT_REPO_URL = GIT_REPO_URL.replace('https://', '')

                sh "./set.envs.sh ${VARS} --set pump.bot.repo.url='https://${GIT_USERNAME}:${GIT_TOKEN}@${GIT_CONFIG_URL}' --set telethon.bot.name='${TELETHON_BOT_NAME}' --set telethon.bot.token='${TELETHON_BOT_TOKEN}' --set telethon.api.phone='${TELETHON_API_PHONE}' --set telethon.api.id='${TELETHON_API_ID}' --set telethon.api.hash='${TELETHON_API_HASH}' --set telethon.user.id='${TELETHON_USER_ID}' --set telethon.bot.id=0 --set kucoin.api.secret='${KUCOIN_API_SECRET}' --set kucoin.api.secret='${KUCOIN_API_KEY}' --set kucoin.api.key.passphrase='${KUCOIN_API_KEY_PASSPHRASE}' --set mexc.api.key='${MEXC_API_KEY}' --set mexc.api.secret='${MEXC_API_SECRET}' --dir ./ --exclude 'Jenkinsfile' --exclude '*.md' --exclude '*.sh' --exclude '*.py' --exclude '*.ini' --exclude '*.example' --exclude '*.session'"

                // if you have $ inside password - just use \$ (dolar escape) inside this var at editing credentials in jenkins!

            }
        }
    } catch(error) {

        throw(error)

    }
}

def test(JENKINS_REPO_DIR) {

    echo """
        Test Pump Bot On K8S
    """

    try {

        dir("${JENKINS_REPO_DIR}") {

            sh """
                export KUBECONFIG="/home/jenkins/.kube/config";

                kubectl apply -f ./k8s.manifests/storage.yml;
                kubectl apply -f ./k8s.manifests/config.yml;
                kubectl apply -f ./k8s.manifests/deployment.test.yml;
            """

            // Wait until the pod in the deployment is running the tests
            waitUntil {
                def podName = sh(script: "export KUBECONFIG=\"/home/jenkins/.kube/config\"; kubectl get pods -l app=pump-bot-api-tests -o jsonpath='{.items[0].metadata.name}'", returnStdout: true).trim()
                def status = sh(script: "export KUBECONFIG=\"/home/jenkins/.kube/config\"; kubectl get pod ${podName} -o jsonpath='{.status.phase}'", returnStdout: true).trim()
                return status == 'Running' || status == 'Succeeded' || status == 'Failed'
            }

            // Capture the pod name after it’s up and running
            def podName = sh(script: "export KUBECONFIG=\"/home/jenkins/.kube/config\"; kubectl get pods -l app=pump-bot-api-tests -o jsonpath='{.items[0].metadata.name}'", returnStdout: true).trim()

            // Wait until the tests are finished by checking container logs
            waitUntil {
                // Sleep for 1 minute before the next check
                sleep time: 1, unit: 'MINUTES'

                def testLogs = sh(script: "export KUBECONFIG=\"/home/jenkins/.kube/config\"; kubectl logs ${podName} -c pump-bot-api-tests", returnStdout: true).trim()
                echo "Test Logs:\n${testLogs}"
                return testLogs.contains("summary") || testLogs.contains("tox")  // assuming `tox` will indicate completion
            }

            // After tests, check if logs contain failure keywords
            def finalLogs = sh(script: "export KUBECONFIG=\"/home/jenkins/.kube/config\"; kubectl logs ${podName} -c pump-bot-api-tests", returnStdout: true).trim()
            if (finalLogs.contains("FAILED")) {
                error("TESTS FAILED.")
            }

        }
    } catch(error) {

        throw(error)
    }
}

def deploy(JENKINS_REPO_DIR) {

    echo """
        Deploy Pump Bot On K8S
    """

    try {

        dir("${JENKINS_REPO_DIR}") {

            sh """
                export KUBECONFIG="/home/jenkins/.kube/config";

                kubectl apply -f ./k8s.manifests/storage.yml;
                kubectl apply -f ./k8s.manifests/config.yml;
                kubectl apply -f ./k8s.manifests/deployment.yml;
            """
        }

    } catch(error) {

        throw(error)
    }
}


pipeline {

    agent {

        node {

            label "docker-builder && linux"

        }
    }

    environment {

        OS_NAME=""

        JENKINS_REPO_PUMP_SCRIPT_DIR = "${JENKINS_AGENT_WORKDIR}/pump.script"

        GIT_REPO_PUMP_SCRIPT_URL="https://git.00x097.com/tbs093a/pump.bot.git"

        JENKINS_USER_ID = 1000
        JENKINS_GROUP_ID = 1000

    }

    triggers {

        GenericTrigger(

            genericVariables: [
                [
                    key: 'DATA_SOURCE_BRANCH',
                    value: '$.DATA_SOURCE_BRANCH'
                ],
                [
                    key: 'TESTS',
                    value: '$.TESTS'
                ],
                [
                    key: 'DEPLOY',
                    value: '$.DEPLOY'
                ],
            ],
            token: '077ff7e0-8460-4a63-9a33-71503bbad374'
        )
    }

    stages {

        stage('Setup Parameters') {

            steps {

                script {

                    if ("${NODE_NAME}".contains("windows")) {
                        OS_NAME = "windows"
                    } else {
                        OS_NAME = "linux"
                    }

                    properties([
                        parameters([
                            string(
                                defaultValue: 'master',
                                description: 'Select <b>Pump Bot</b> data source branch for the build & deploy',
                                name: 'DATA_SOURCE_BRANCH'
                            ),
                            booleanParam(
                                defaultValue: false,
                                description: 'Enable if you want <b>run Pump Bot tests only</b>.',
                                name: 'TESTS'
                            ),
                            booleanParam(
                                defaultValue: true,
                                description: 'Enable if you want <b>run Pump Bot</b> for capture pump singnals from telegram and invest automatically',
                                name: 'DEPLOY'
                            )
                        ])
                    ])
                }
            }
        }

        stage('Clean Workspace') {

            steps {

                script {

                    catchError(
                        buildresult: 'SUCCESS',
                        stageresult: 'UNSTABLE'
                    ) {

                        delete_directory(
                            "${JENKINS_REPO_PUMP_SCRIPT_DIR}",
                            OS_NAME
                        )
                    }
                }
            }
        }

        stage('Fetch Script Repositories') {

            steps {

                script {

                    parallel(

                        pump_bot_script: {

                            fetch_git_repository(
                                "Pump Bot (on VM - ${NODE_NAME})",
                                "${JENKINS_REPO_PUMP_SCRIPT_DIR}",
                                "${DATA_SOURCE_BRANCH}",
                                "${GIT_REPO_PUMP_SCRIPT_URL}"
                            )
                        }
                    )
                }
            }
        }

        stage('Set Env Vars') {

            steps {

                script {

                    catchError(
                        buildresult: 'FAILURE',
                        stageresult: 'FAILURE'
                    ) {

                        set_env_vars(
                            "${JENKINS_REPO_PUMP_SCRIPT_DIR}",
                            "${GIT_REPO_PUMP_SCRIPT_URL}",
                            ""
                        )
                    }
                }
            }
        }

        stage('Test Pump Bot On K8S') {

            when {

                expression {

                    "${TESTS}" == "true"
                }
            }

            steps {

                echo """
                    Test Pump Bot On K8S
                """

                catchError(
                    buildResult: 'SUCCESS',
                    stageResult: 'UNSTABLE'
                ) {

                    test(
                        "${JENKINS_REPO_PUMP_SCRIPT_DIR}"
                    )
                }
            }
        }

        stage('Deploy Pump Bot On K8S') {

            when {

                expression {

                    "${DEPLOY}" == "true"
                }
            }

            steps {

                echo """
                    Deploy Pump Bot On K8S
                """

                catchError(
                    buildResult: 'FAILURE',
                    stageResult: 'FAILURE'
                ) {

                    deploy(
                        "${JENKINS_REPO_PUMP_SCRIPT_DIR}"
                    )

                }
            }
        }

    }
}

