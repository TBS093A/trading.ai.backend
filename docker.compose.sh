#!/bin/bash

# Zmienne środowiskowe - PostgreSQL
DB_NAME="trading_bot_ai_db"
DB_USER="trading_bot_ai_user"
DB_PASSWORD="trading_bot_ai_pass"
DB_PORT="5432"
POSTGRES_CONTAINER_NAME="trading_bot_ai_postgres"

# Zmienne środowiskowe - RabbitMQ
RABBITMQ_CONTAINER_NAME="trading_bot_ai_rabbitmq"
RABBITMQ_USER="trading_bot_ai_rabbit"
RABBITMQ_PASSWORD="trading_bot_ai_rabbit_pass"
RABBITMQ_PORT="5672"
RABBITMQ_MANAGEMENT_PORT="15672"

# Zmienne środowiskowe - Redis
REDIS_CONTAINER_NAME="trading_bot_ai_redis"
REDIS_PORT="6379"
REDIS_PASSWORD="trading_bot_ai_redis_pass"

# Eksport zmiennych środowiskowych
export DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@localhost:${DB_PORT}/${DB_NAME}"
export CELERY_BROKER_URL="pyamqp://${RABBITMQ_USER}:${RABBITMQ_PASSWORD}@localhost:${RABBITMQ_PORT}//"
export CELERY_RESULT_BACKEND="redis://:${REDIS_PASSWORD}@localhost:${REDIS_PORT}/0"

echo "🚀 Starting Trading Bot AI Infrastructure..."

# Uruchomienie PostgreSQL
echo "📦 Starting PostgreSQL container..."
docker run \
    --name "${POSTGRES_CONTAINER_NAME}" \
    -e POSTGRES_DB="${DB_NAME}" \
    -e POSTGRES_USER="${DB_USER}" \
    -e POSTGRES_PASSWORD="${DB_PASSWORD}" \
    -p "${DB_PORT}:5432" \
    --restart unless-stopped \
    -d \
    postgres:14-alpine

# Uruchomienie RabbitMQ dla Celery
echo "🐰 Starting RabbitMQ container..."
docker run \
    --name "${RABBITMQ_CONTAINER_NAME}" \
    -e RABBITMQ_DEFAULT_USER="${RABBITMQ_USER}" \
    -e RABBITMQ_DEFAULT_PASS="${RABBITMQ_PASSWORD}" \
    -p "${RABBITMQ_PORT}:5672" \
    -p "${RABBITMQ_MANAGEMENT_PORT}:15672" \
    --restart unless-stopped \
    -d \
    rabbitmq:3-management-alpine

# Uruchomienie Redis dla Celery Result Backend
echo "🔴 Starting Redis container..."
docker run \
    --name "${REDIS_CONTAINER_NAME}" \
    -p "${REDIS_PORT}:6379" \
    --restart unless-stopped \
    -d \
    redis:7-alpine redis-server --requirepass "${REDIS_PASSWORD}"

echo "✅ Infrastructure started successfully!"
echo "📊 PostgreSQL: localhost:${DB_PORT}"
echo "🐰 RabbitMQ: localhost:${RABBITMQ_PORT}"
echo "🌐 RabbitMQ Management: http://localhost:${RABBITMQ_MANAGEMENT_PORT}"
echo "   User: ${RABBITMQ_USER}"
echo "   Pass: ${RABBITMQ_PASSWORD}"
echo "🔴 Redis: localhost:${REDIS_PORT}"
echo "   Pass: ${REDIS_PASSWORD}"
echo ""
echo "🔧 Environment variables:"
echo "   DATABASE_URL=${DATABASE_URL}"
echo "   CELERY_BROKER_URL=${CELERY_BROKER_URL}"
echo "   CELERY_RESULT_BACKEND=${CELERY_RESULT_BACKEND}"
