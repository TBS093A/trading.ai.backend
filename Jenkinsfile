/*
 * W Jenkins dodaj Secret text (lub odpowiednie credential), ID dokładnie jak poniżej:
 *   trading-ai-openai-api-key
 *   trading-ai-crypto-panic-api-key
 *   trading-ai-gnews-api-key
 *   trading-ai-coindesk-api-key
 *   trading-ai-minio-access-key
 *   trading-ai-minio-secret-key
 *   trading-ai-database-credentials (Username with password)
 *   trading-ai-rabbitmq-credentials (Username with password)
 *   trading-ai-redis-password
 * (Istniejące: git-gitea-tbs093a, telegram-*, kucoin-*, mexc-* — jak w withCredentials.)
 */

def escSql(s) {
    try {
        if (s == null) {
            return ''
        }
        return s.toString().replace("'", "'\\''")
    } catch (Exception e) {
        echo "escSql failed: ${e.message}"
        throw e
    }
}

def generateK8sConfigFromTemplate() {
    try {
        withCredentials(
            [
            usernamePassword(
                credentialsId: 'git-gitea-tbs093a',
                passwordVariable: 'GIT_TOKEN',
                usernameVariable: 'GIT_USERNAME'
            ),
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
                usernameVariable: 'KUCOIN_USERNAME_UNUSED'
            ),
            usernamePassword(
                credentialsId: 'mexc-zukkamil-api-secrets',
                passwordVariable: 'MEXC_API_SECRET',
                usernameVariable: 'MEXC_API_KEY'
            ),
            string(credentialsId: 'trading-ai-openai-api-key', variable: 'OPENAI_API_KEY'),
            string(credentialsId: 'trading-ai-crypto-panic-api-key', variable: 'CRYPTO_PANIC_API_KEY'),
            string(credentialsId: 'trading-ai-gnews-api-key', variable: 'GNEWS_API_KEY'),
            string(credentialsId: 'trading-ai-coindesk-api-key', variable: 'COINDESK_API_KEY'),
            string(credentialsId: 'trading-ai-minio-access-key', variable: 'MINIO_ACCESS_KEY'),
            string(credentialsId: 'trading-ai-minio-secret-key', variable: 'MINIO_SECRET_KEY'),
            usernamePassword(
                credentialsId: 'trading-ai-database-credentials',
                usernameVariable: 'DATABASE_CREDS_USERNAME',
                passwordVariable: 'DATABASE_CREDS_PASSWORD'
            ),
            usernamePassword(
                credentialsId: 'trading-ai-rabbitmq-credentials',
                usernameVariable: 'RABBITMQ_CREDS_USERNAME',
                passwordVariable: 'RABBITMQ_CREDS_PASSWORD'
            ),
            string(credentialsId: 'trading-ai-redis-password', variable: 'REDIS_PASSWORD_PLAIN'),
        ]
    ) {
        def backendRepoUrl = escSql("https://${env.GIT_USERNAME}:${env.GIT_TOKEN}@${params.GIT_REPO_PATH_BACKEND}")
        def frontendRepoUrl = escSql("https://${env.GIT_USERNAME}:${env.GIT_TOKEN}@${params.GIT_REPO_PATH_FRONTEND}")

        sh """
            chmod +x ./set.envs.sh
            ./set.envs.sh \\
                --set trading.ai.backend.repo.url='${backendRepoUrl}' \\
                --set trading.ai.backend.repo.branch='${escSql(params.DATA_SOURCE_BRANCH)}' \\
                --set trading.ai.frontend.repo.url='${frontendRepoUrl}' \\
                --set trading.ai.frontend.repo.branch='${escSql(params.FRONTEND_REPO_BRANCH)}' \\
                --set react.app.api.url='${escSql(params.REACT_APP_API_URL)}' \\
                --set telethon.bot.name='${escSql(env.TELETHON_BOT_NAME)}' \\
                --set telethon.bot.token='${escSql(env.TELETHON_BOT_TOKEN)}' \\
                --set telethon.api.phone='${escSql(env.TELETHON_API_PHONE)}' \\
                --set telethon.api.id='${escSql(env.TELETHON_API_ID)}' \\
                --set telethon.api.hash='${escSql(env.TELETHON_API_HASH)}' \\
                --set telethon.user.id='${escSql(env.TELETHON_USER_ID)}' \\
                --set telethon.bot.id='${escSql(params.TELETHON_BOT_ID)}' \\
                --set kucoin.api.secret='${escSql(env.KUCOIN_API_SECRET)}' \\
                --set kucoin.api.key='${escSql(env.KUCOIN_API_KEY)}' \\
                --set kucoin.api.key.passphrase='${escSql(env.KUCOIN_API_KEY_PASSPHRASE)}' \\
                --set mexc.api.key='${escSql(env.MEXC_API_KEY)}' \\
                --set mexc.api.secret='${escSql(env.MEXC_API_SECRET)}' \\
                --set openai.api.key='${escSql(env.OPENAI_API_KEY)}' \\
                --set crypto.panic.api.key='${escSql(env.CRYPTO_PANIC_API_KEY)}' \\
                --set gnews.api.key='${escSql(env.GNEWS_API_KEY)}' \\
                --set coindesk.api.key='${escSql(env.COINDESK_API_KEY)}' \\
                --set minio.access.key='${escSql(env.MINIO_ACCESS_KEY)}' \\
                --set minio.secret.key='${escSql(env.MINIO_SECRET_KEY)}' \\
                --set minio.endpoint='${escSql(params.MINIO_ENDPOINT)}' \\
                --set minio.secure='${escSql(params.MINIO_SECURE)}' \\
                --set minio.bucket.name='${escSql(params.MINIO_BUCKET_NAME)}' \\
                --set local.storage.is.enabled='${escSql(params.LOCAL_STORAGE_IS_ENABLED)}' \\
                --set local.storage.path='${escSql(params.LOCAL_STORAGE_PATH)}' \\
                --set database.username='${escSql(env.DATABASE_CREDS_USERNAME)}' \\
                --set database.password='${escSql(env.DATABASE_CREDS_PASSWORD)}' \\
                --set database.host='${escSql(params.DATABASE_HOST)}' \\
                --set database.port='${escSql(params.DATABASE_PORT)}' \\
                --set database.schema='${escSql(params.DATABASE_SCHEMA)}' \\
                --set rabbitmq.username='${escSql(env.RABBITMQ_CREDS_USERNAME)}' \\
                --set rabbitmq.password='${escSql(env.RABBITMQ_CREDS_PASSWORD)}' \\
                --set rabbitmq.port='${escSql(params.CELERY_BROKER_PORT)}' \\
                --set rabbitmq.management.port='${escSql(params.CELERY_BROKER_MANAGEMENT_PORT)}' \\
                --set redis.password='${escSql(env.REDIS_PASSWORD_PLAIN)}' \\
                --set redis.port='${escSql(params.CELERY_RESULT_BACKEND_PORT)}' \\
                --dir ./k8s.manifests
        """
        }
    } catch (Throwable e) {
        echo "generateK8sConfigFromTemplate failed: ${e.message}"
        throw e
    }
}

def deployTradingAiK8s() {
    try {
        sh """
            export KUBECONFIG="/home/jenkins/.kube/config"
            chmod +x ./k8s.manifests/deploy.sh
            cd ./k8s.manifests
            ./deploy.sh deploy
        """
    } catch (Exception e) {
        echo "Error deploying Trading AI on K8s: ${e.message}"
        throw e
    }
}

def deleteTradingAiK8sManifests() {
    try {
        sh """
            export KUBECONFIG="/home/jenkins/.kube/config"
            cd ./k8s.manifests
            kubectl delete -f deployment-sync.yml --ignore-not-found=true
            kubectl delete -f deployment-rest-api.yml --ignore-not-found=true
            kubectl delete -f ingress-frontend.yml --ignore-not-found=true
            kubectl delete -f deployment-frontend.yml --ignore-not-found=true
            kubectl delete -f daemonset-celery-workers.yml --ignore-not-found=true
            kubectl delete -f deployment-rabbitmq.yml --ignore-not-found=true
            kubectl delete -f deployment-redis.yml --ignore-not-found=true
            kubectl delete -f services.yml --ignore-not-found=true
            kubectl delete -f config-env.yml --ignore-not-found=true
        """
    } catch (Exception e) {
        echo "deleteTradingAiK8sManifests failed: ${e.message}"
        throw e
    }
}

pipeline {

    agent {
        node {
            label 'docker-builder && linux'
        }
    }

    triggers {
        GenericTrigger(
            genericVariables: [
                [key: 'DATA_SOURCE_BRANCH', value: '$.DATA_SOURCE_BRANCH'],
                [key: 'TESTS', value: '$.TESTS'],
                [key: 'DEPLOY', value: '$.DEPLOY'],
            ],
            token: '077ff7e0-8460-4a63-9a33-71503bbad374'
        )
    }

    stages {

        stage('Setup parameters') {
            steps {
                script {
                    properties([
                        parameters([
                            string(
                                defaultValue: 'master',
                                description: 'Branch repozytorium <b>trading.ai.backend</b> (klon w init k8s)',
                                name: 'DATA_SOURCE_BRANCH'
                            ),
                            string(
                                defaultValue: 'main',
                                description: 'Branch repozytorium <b>trading.ai.frontend</b>',
                                name: 'FRONTEND_REPO_BRANCH'
                            ),
                            string(
                                defaultValue: 'git.00x097.com/tbs093a/trading.ai.backend.git',
                                description: 'Ścieżka Git backendu <b>bez</b> https:// (token dokleja Jenkins z git-gitea-tbs093a)',
                                name: 'GIT_REPO_PATH_BACKEND'
                            ),
                            string(
                                defaultValue: 'git.00x097.com/tbs093a/trading.ai.frontend.git',
                                description: 'Ścieżka Git frontendu <b>bez</b> https://',
                                name: 'GIT_REPO_PATH_FRONTEND'
                            ),
                            string(
                                defaultValue: 'trading-ai-backend-rest-api-service.default.svc.cluster.local',
                                description: 'REACT_APP_API_URL (z perspektywy przeglądarki — produkcja: publiczny URL API)',
                                name: 'REACT_APP_API_URL'
                            ),
                            string(
                                defaultValue: 'postgresql.default.svc.cluster.local',
                                name: 'DATABASE_HOST'
                            ),
                            string(
                                defaultValue: '5432',
                                name: 'DATABASE_PORT'
                            ),
                            string(
                                defaultValue: 'trading_ai_backend_database',
                                name: 'DATABASE_SCHEMA'
                            ),
                            string(
                                defaultValue: '5672',
                                name: 'CELERY_BROKER_PORT'
                            ),
                            string(
                                defaultValue: '15672',
                                name: 'CELERY_BROKER_MANAGEMENT_PORT'
                            ),
                            string(
                                defaultValue: '6379',
                                name: 'CELERY_RESULT_BACKEND_PORT'
                            ),
                            string(
                                defaultValue: 'api.storage.xgpu.site',
                                name: 'MINIO_ENDPOINT'
                            ),
                            string(
                                defaultValue: 'true',
                                name: 'MINIO_SECURE'
                            ),
                            string(
                                defaultValue: 'trading.ai.charts',
                                name: 'MINIO_BUCKET_NAME'
                            ),
                            string(
                                defaultValue: 'false',
                                name: 'LOCAL_STORAGE_IS_ENABLED'
                            ),
                            string(
                                defaultValue: './local_storage',
                                name: 'LOCAL_STORAGE_PATH'
                            ),
                            string(
                                defaultValue: '7411839891',
                                description: 'TELETHON_BOT_ID (numeryczny ID bota)',
                                name: 'TELETHON_BOT_ID'
                            ),
                            booleanParam(
                                defaultValue: true,
                                description: 'Uruchom <b>k8s.manifests/deploy.sh deploy</b> po wygenerowaniu config-env.yml',
                                name: 'DEPLOY'
                            ),
                            booleanParam(
                                defaultValue: false,
                                description: '<b>Teardown:</b> <code>kubectl delete -f</code> na manifestach (jak cleanup w deploy.sh) — przed generowaniem configu; PostgreSQL na klastrze bez zmian',
                                name: 'K8S_DELETE_MANIFESTS'
                            ),
                        ])
                    ])
                }
            }
        }

        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Delete Trading AI from K8s (kubectl delete)') {
            when {
                expression {
                    params.K8S_DELETE_MANIFESTS == true || params.K8S_DELETE_MANIFESTS?.toString() == 'true'
                }
            }
            steps {
                echo 'K8S_DELETE_MANIFESTS: kubectl delete -f (manifesty w k8s.manifests/)'
                script {
                    catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                        deleteTradingAiK8sManifests()
                    }
                }
            }
        }

        stage('Clean generated k8s config') {
            steps {
                sh 'rm -f k8s.manifests/config-env.yml || true'
            }
        }

        stage('Generate k8s config-env.yml') {
            steps {
                script {
                    catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                        generateK8sConfigFromTemplate()
                    }
                }
            }
        }

        stage('Deploy Trading AI on K8s') {
            when {
                expression {
                    params.DEPLOY == true || params.DEPLOY?.toString() == 'true'
                }
            }
            steps {
                echo 'Deploy: k8s.manifests/deploy.sh deploy'
                script {
                    catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                        deployTradingAiK8s()
                    }
                }
            }
        }
    }
}
