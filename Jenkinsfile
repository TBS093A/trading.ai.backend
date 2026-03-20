/*
 * W Jenkins dodaj Secret text (lub odpowiednie credential), ID dokładnie jak poniżej:
 *   trading-ai-openai-api-key
 *   trading-ai-crypto-panic-api-key
 *   trading-ai-gnews-api-key
 *   trading-ai-coindesk-api-key
 *   trading-ai-minio-access-key
 *   trading-ai-minio-secret-key
 *   trading-ai-database-password
 *   trading-ai-rabbitmq-password
 *   trading-ai-redis-password
 * (Istniejące: git-gitea-tbs093a, telegram-*, kucoin-*, mexc-* — jak w withCredentials.)
 */

def escSql(String s) {
    if (s == null) {
        return ''
    }
    return s.replace("'", "'\\''")
}

def generateK8sConfigFromTemplate() {
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
            string(credentialsId: 'trading-ai-database-password', variable: 'DATABASE_PASSWORD'),
            string(credentialsId: 'trading-ai-rabbitmq-password', variable: 'RABBITMQ_PASSWORD_PLAIN'),
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
                --set database.username='${escSql(params.DATABASE_USERNAME)}' \\
                --set database.password='${escSql(env.DATABASE_PASSWORD)}' \\
                --set database.host='${escSql(params.DATABASE_HOST)}' \\
                --set database.port='${escSql(params.DATABASE_PORT)}' \\
                --set database.schema='${escSql(params.DATABASE_SCHEMA)}' \\
                --set rabbitmq.username='${escSql(params.CELERY_BROKER_USERNAME)}' \\
                --set rabbitmq.password='${escSql(env.RABBITMQ_PASSWORD_PLAIN)}' \\
                --set rabbitmq.port='${escSql(params.CELERY_BROKER_PORT)}' \\
                --set rabbitmq.management.port='${escSql(params.CELERY_BROKER_MANAGEMENT_PORT)}' \\
                --set redis.password='${escSql(env.REDIS_PASSWORD_PLAIN)}' \\
                --set redis.port='${escSql(params.CELERY_RESULT_BACKEND_PORT)}' \\
                --dir ./k8s.manifests
        """
    }
}

def deployTradingAiK8s() {
    sh """
        export KUBECONFIG="/home/jenkins/.kube/config"
        chmod +x ./k8s.manifests/deploy.sh
        cd ./k8s.manifests
        ./deploy.sh deploy
    """
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
                                defaultValue: 'master',
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
                                defaultValue: 'http://localhost:9090',
                                description: 'REACT_APP_API_URL (z perspektywy przeglądarki — produkcja: publiczny URL API)',
                                name: 'REACT_APP_API_URL'
                            ),
                            string(
                                defaultValue: 'trading_ai_backend_user',
                                name: 'DATABASE_USERNAME'
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
                                defaultValue: 'trading_bot_ai_rabbit',
                                description: 'RabbitMQ user (ConfigMap RABBITMQ_USER)',
                                name: 'CELERY_BROKER_USERNAME'
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
