#!/bin/bash
set -euo pipefail

# SERVICE_MODE wybiera ktory tox environment odpalic - musi byc jednym z tych
# pre-zbudowanych w Dockerfile (RUN tox --notest -e ...).
: "${SERVICE_MODE:?SERVICE_MODE musi byc ustawiony na jeden z: sync-controller, rest-api-controller, rest-api-celery-worker}"

case "$SERVICE_MODE" in
  sync-controller|rest-api-controller|rest-api-celery-worker)
    ;;
  *)
    echo "Nieznany SERVICE_MODE: $SERVICE_MODE (oczekiwano: sync-controller | rest-api-controller | rest-api-celery-worker)" >&2
    exit 1
    ;;
esac

# Zbudowanie zlozonych URL-i polaczen z pojedynczych zmiennych (DATABASE_USERNAME,
# DATABASE_PASSWORD, itd.) - dokladnie to co wczesniej robil inline `command:` w
# manifescie k8s. Przeniesione tutaj, zeby nie powielac tych samych 3 linii w
# trzech osobnych deploymentach.
export DATABASE_URL="postgresql://${DATABASE_USERNAME}:${DATABASE_PASSWORD}@${DATABASE_HOST}:${DATABASE_PORT}/${DATABASE_SCHEMA}"
export CELERY_BROKER_URL="pyamqp://${RABBITMQ_USER}:${RABBITMQ_PASSWORD}@trading-ai-backend-rabbitmq-service:${RABBITMQ_PORT}//"
export CELERY_RESULT_BACKEND="redis://:${REDIS_PASSWORD}@trading-ai-backend-redis-service:${REDIS_PORT}/0"

# --skip-pkg-install: venv juz zbudowany w obrazie (Dockerfile), nie instaluj nic
# w runtime - to caly sens tej zmiany (bylo: git clone + pip install tox przy
# kazdym restarcie poda).
exec python -m tox run -e "$SERVICE_MODE" --skip-pkg-install
