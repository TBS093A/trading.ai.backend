#!/bin/sh
set -eu

# SERVICE_MODE wybiera, ktory proces uruchomic. Komendy musza zgadzac sie z `commands =`
# odpowiednich [testenv:...] w tox.ini (tam uruchamia sie to lokalnie przez tox).
: "${SERVICE_MODE:?SERVICE_MODE musi byc ustawiony na jeden z: sync-controller, rest-api-controller, rest-api-celery-worker}"

case "$SERVICE_MODE" in
  sync-controller)
    set -- python ./main_controller_sync.py
    ;;
  rest-api-controller)
    set -- python ./main_controller_rest_api.py
    ;;
  rest-api-celery-worker)
    set -- celery -A src.controller_rest_celery_worker worker --loglevel=info --queues=celery,sync_queue,analysis_queue
    ;;
  *)
    echo "Nieznany SERVICE_MODE: $SERVICE_MODE (oczekiwano: sync-controller | rest-api-controller | rest-api-celery-worker)" >&2
    exit 1
    ;;
esac

# Zbudowanie zlozonych URL-i polaczen z pojedynczych zmiennych (DATABASE_USERNAME,
# DATABASE_PASSWORD, itd.) - wczesniej robil to inline `command:` w manifescie k8s.
export DATABASE_URL="postgresql://${DATABASE_USERNAME}:${DATABASE_PASSWORD}@${DATABASE_HOST}:${DATABASE_PORT}/${DATABASE_SCHEMA}"
export CELERY_BROKER_URL="pyamqp://${RABBITMQ_USER}:${RABBITMQ_PASSWORD}@trading-ai-backend-rabbitmq-service:${RABBITMQ_PORT}//"
export CELERY_RESULT_BACKEND="redis://:${REDIS_PASSWORD}@trading-ai-backend-redis-service:${REDIS_PORT}/0"

exec "$@"
