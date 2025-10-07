#!/bin/bash

source .env;

export POSTGRES_CONTAINER_NAME="trading_bot_ai_postgres"
export RABBITMQ_CONTAINER_NAME="trading_bot_ai_rabbitmq"
export REDIS_CONTAINER_NAME="trading_bot_ai_redis"

echo "🚀 Starting Trading Bot AI Infrastructure..."

# Uruchomienie PostgreSQL
echo "📦 Starting PostgreSQL container..."
docker run \
    --name "${POSTGRES_CONTAINER_NAME}" \
    -e POSTGRES_DB="${DATABASE_SCHEMA}" \
    -e POSTGRES_USER="${DATABASE_USERNAME}" \
    -e POSTGRES_PASSWORD="${DATABASE_PASSWORD}" \
    -p "${DATABASE_PORT}:5432" \
    --restart unless-stopped \
    -d \
    postgres:14-alpine

# Uruchomienie RabbitMQ dla Celery
echo "🐰 Starting RabbitMQ container..."
docker run \
    --name "${RABBITMQ_CONTAINER_NAME}" \
    -e RABBITMQ_DEFAULT_USER="${CELERY_BROKER_USERNAME}" \
    -e RABBITMQ_DEFAULT_PASS="${CELERY_BROKER_PASSWORD}" \
    -p "${CELERY_BROKER_PORT}:5672" \
    -p "${CELERY_BROKER_MANAGEMENT_PORT}:15672" \
    --restart unless-stopped \
    -d \
    rabbitmq:3-management-alpine

# Uruchomienie Redis dla Celery Result Backend
echo "🔴 Starting Redis container..."
docker run \
    --name "${REDIS_CONTAINER_NAME}" \
    -p "${CELERY_RESULT_BACKEND_PORT}:6379" \
    --restart unless-stopped \
    -d \
    redis:7-alpine redis-server --requirepass "${CELERY_RESULT_BACKEND_PASSWORD}"

echo "✅ Infrastructure started successfully!"
echo "📊 PostgreSQL: localhost:${DATABASE_PORT}"
echo "🐰 RabbitMQ: localhost:${CELERY_BROKER_PORT}"
echo "🌐 RabbitMQ Management: http://localhost:${CELERY_BROKER_MANAGEMENT_PORT}"
echo "   User: ${CELERY_BROKER_USERNAME}"
echo "   Pass: ${CELERY_BROKER_PASSWORD}"
echo "🔴 Redis: localhost:${CELERY_RESULT_BACKEND_PORT}"
echo "   Pass: ${CELERY_RESULT_BACKEND_PASSWORD}"
echo ""
echo "🔧 Environment variables:"
echo "   DATABASE_URL=${DATABASE_URL}"
echo "   CELERY_BROKER_URL=${CELERY_BROKER_URL}"
echo "   CELERY_RESULT_BACKEND=${CELERY_RESULT_BACKEND_URL}"
