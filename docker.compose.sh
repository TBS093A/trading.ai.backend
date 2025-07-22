#!/bin/bash

# Zmienne środowiskowe
DB_NAME="trading_bot_ai_db"
DB_USER="trading_bot_ai_user"
DB_PASSWORD="trading_bot_ai_pass"
DB_PORT="5432"
VOLUME_NAME="trading_bot_ai_db"

export DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@localhost:${DB_PORT}/${DB_NAME}"

docker run \
    --name "${CONTAINER_NAME}" \
    -e POSTGRES_DB="${DB_NAME}" \
    -e POSTGRES_USER="${DB_USER}" \
    -e POSTGRES_PASSWORD="${DB_PASSWORD}" \
    -p "${DB_PORT}:5432" \
    --restart unless-stopped \
    -d \
    postgres:14-alpine
