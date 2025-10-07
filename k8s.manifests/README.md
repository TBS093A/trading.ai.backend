# Kubernetes Manifests - Trading AI Backend

Konfiguracja Kubernetes dla kompletnego ekosystemu Trading AI Backend.

## 📋 Architektura

System składa się z następujących komponentów:

### Infrastructure Services
- **PostgreSQL** - Używamy istniejącego PostgreSQL na klastrze (`postgresql.default.svc.cluster.local`)
- **RabbitMQ** - Message broker dla Celery
- **Redis** - Cache i Celery result backend

### Application Services
- **Sync Controller** - Kontroler synchronizacji danych (main_controller_sync.py)
- **REST API Controller** - API REST (main_controller_rest_api.py)
- **Celery Workers** - DaemonSet (1 worker per node)

## 🚀 Quick Start

### 1. Konfiguracja zmiennych środowiskowych

Użyj skryptu `set.envs.sh` do ustawienia wszystkich placeholderów:

```bash
cd /home/tbs093a/Projects/trading.ai.backend;

source .env;

./set.envs.sh \
  --set pump.bot.repo.url=https://github.com/your-org/trading.ai.backend.git \
  --set trading.ai.backend.repo.url=$REPO_URL \
  --set telethon.bot.name=$TELETHON_BOT_NAME \
  --set telethon.bot.token=$TELETHON_BOT_TOKEN \
  --set telethon.api.phone=$TELETHON_API_PHONE \
  --set telethon.api.id=$TELETHON_API_ID \
  --set telethon.api.hash=$TELETHON_API_HASH \
  --set telethon.user.id=$TELETHON_USER_ID \
  --set telethon.bot.id=$TELETHON_BOT_ID \
  --set kucoin.api.secret=$KUCOIN_API_SECRET \
  --set kucoin.api.key=$KUCOIN_API_KEY \
  --set kucoin.api.key.passphrase=$KUCOIN_API_KEY_PASSPHRASE \
  --set mexc.api.key=$MEXC_API_KEY \
  --set mexc.api.secret=$MEXC_API_SECRET \
  --set openai.api.key=$OPENAI_API_KEY \
  --set crypto.panic.api.key=$CRYPTO_PANIC_API_KEY \
  --set gnews.api.key=$GNEWS_API_KEY \
  --set coindesk.api.key=$COINDESK_API_KEY \
  --set minio.access.key=$MINIO_ACCESS_KEY \
  --set minio.secret.key=$MINIO_SECRET_KEY \
  --set minio.endpoint=$MINIO_ENDPOINT \
  --set minio.secure=$MINIO_SECURE \
  --set minio.bucket.name=$MINIO_BUCKET_NAME \
  --set database.username=$DATABASE_USERNAME \
  --set database.password=$DATABASE_PASSWORD \
  --set database.host=$DATABASE_HOST \
  --set database.port=$DATABASE_PORT \
  --set database.schema=$DATABASE_SCHEMA \
  --set rabbitmq.username=$CELERY_BROKER_USERNAME \
  --set rabbitmq.password=$CELERY_BROKER_PASSWORD \
  --set rabbitmq.port=$CELERY_BROKER_PORT \
  --set rabbitmq.management.port=$CELERY_BROKER_MANAGEMENT_PORT \
  --set redis.password=$CELERY_RESULT_BACKEND_PASSWORD \
  --set redis.port=$CELERY_RESULT_BACKEND_PORT \
  --dir ./k8s.manifests
```

### 2. Deploy kolejno wszystkie komponenty

```bash
# 1. ConfigMap i Secret (zmienne środowiskowe)
kubectl apply -f k8s.manifests/config-env.yml

# 2. Storage (PersistentVolume dla aplikacji)
kubectl apply -f k8s.manifests/storage.yml

# 3. Infrastructure Services (RabbitMQ, Redis)
# Uwaga: PostgreSQL używamy istniejący na klastrze (postgresql.default.svc.cluster.local)
kubectl apply -f k8s.manifests/deployment-rabbitmq.yml
kubectl apply -f k8s.manifests/deployment-redis.yml

# Poczekaj aż infrastructure services będą ready
kubectl wait --for=condition=ready pod -l component=message-broker --timeout=300s
kubectl wait --for=condition=ready pod -l component=cache --timeout=300s

# 4. Application Services
kubectl apply -f k8s.manifests/deployment-sync.yml
kubectl apply -f k8s.manifests/deployment-rest-api.yml
kubectl apply -f k8s.manifests/daemonset-celery-workers.yml

# 5. Services (jeśli nie zostały jeszcze stworzone)
kubectl apply -f k8s.manifests/services.yml
```

### 3. Weryfikacja deploymentu

```bash
# Sprawdź status wszystkich podów
kubectl get pods

# Sprawdź logi sync-controller
kubectl logs -l app=sync-controller -f

# Sprawdź logi rest-api-controller
kubectl logs -l app=rest-api-controller -f

# Sprawdź logi celery workers
kubectl logs -l app=celery-workers -f

# Sprawdź services
kubectl get services
```

## 📦 Komponenty

### config-env.yml
ConfigMap i Secret z wszystkimi zmiennymi środowiskowymi:
- ConfigMap: `trading-ai-config` - zmienne non-sensitive
- Secret: `trading-ai-secrets` - wrażliwe dane (API keys, hasła)

### deployment-postgres.optional.yml
**OPCJONALNY** - PostgreSQL 14 Alpine (używamy istniejącego PostgreSQL na klastrze):
- Jeśli chcesz deployować własny PostgreSQL, użyj tego pliku
- Port: 5432
- Service: `postgres-service`
- PVC: `pvc-postgres` (5Gi)
- Resources: 256Mi-512Mi RAM, 250m-500m CPU

**Domyślnie używamy**: `postgresql.default.svc.cluster.local`

### deployment-rabbitmq.yml
RabbitMQ 3 Management:
- Port AMQP: 5672
- Port Management: 15672 (NodePort 30672)
- Service: `rabbitmq-service` (AMQP), `rabbitmq-management` (UI)
- PVC: `pvc-rabbitmq` (2Gi)
- Resources: 256Mi-512Mi RAM, 250m-500m CPU

### deployment-redis.yml
Redis 7 Alpine:
- Port: 6379
- Service: `redis-service`
- PVC: `pvc-redis` (1Gi)
- Resources: 128Mi-256Mi RAM, 100m-250m CPU

### deployment-sync.yml
Sync Controller (1 replica):
- Komenda: `tox run -e sync-controller`
- Używa PVC: `pvc-pump-bot`
- Resources: 512Mi-1Gi RAM, 500m-1000m CPU

### deployment-rest-api.yml
REST API Controller (1 replica):
- Komenda: `tox run -e rest-api-controller`
- Port: 9090 (NodePort 30090)
- Service: `rest-api-service`
- Health checks: `/health`
- Używa PVC: `pvc-pump-bot`
- Resources: 512Mi-1Gi RAM, 500m-1000m CPU

### daemonset-celery-workers.yml
Celery Workers (1 worker per node):
- Komenda: `tox run -e rest-api-celery-worker`
- DaemonSet - każdy node otrzyma 1 worker
- Używa emptyDir (każdy worker ma własny storage)
- Resources: 512Mi-1Gi RAM, 500m-1000m CPU

### services.yml
Wszystkie Services w jednym pliku (dla czytelności):
- `rabbitmq-service` (ClusterIP:5672)
- `rabbitmq-management` (NodePort:30672)
- `redis-service` (ClusterIP:6379)
- `rest-api-service` (NodePort:30090)

**Uwaga**: PostgreSQL service nie jest potrzebny - używamy istniejącego `postgresql.default.svc.cluster.local`

## 🔧 Konfiguracja

### Zmienne środowiskowe

Wszystkie zmienne środowiskowe są skonfigurowane przez:
1. **ConfigMap** `trading-ai-config` - dane non-sensitive
2. **Secret** `trading-ai-secrets` - dane wrażliwe

### URL połączeń

URL-e do baz danych są budowane dynamicznie w deploymentach:

```bash
# PostgreSQL (istniejący na klastrze)
DATABASE_URL="postgresql://${DATABASE_USERNAME}:${DATABASE_PASSWORD}@postgresql.default.svc.cluster.local:${DATABASE_PORT}/${DATABASE_SCHEMA}"

# Celery (nasze serwisy)
CELERY_BROKER_URL="pyamqp://${RABBITMQ_USER}:${RABBITMQ_PASSWORD}@rabbitmq-service:${RABBITMQ_PORT}//"
CELERY_RESULT_BACKEND="redis://:${REDIS_PASSWORD}@redis-service:${REDIS_PORT}/0"
```

## 🌐 Dostęp do serwisów

### REST API
```bash
# Z wewnątrz klastra
http://rest-api-service:9090

# Z zewnątrz (NodePort)
http://<NODE_IP>:30090
```

### RabbitMQ Management UI
```bash
# Z zewnątrz (NodePort)
http://<NODE_IP>:30672

# Credentials:
User: trading_bot_ai_rabbit
Password: <wartość z secret RABBITMQ_PASSWORD>
```

## 📊 Monitoring

### Logi

```bash
# Wszystkie pody aplikacji
kubectl logs -l component=backend -f --all-containers=true

# Sync Controller
kubectl logs -l app=sync-controller -f

# REST API
kubectl logs -l app=rest-api-controller -f

# Celery Workers (wszystkie)
kubectl logs -l app=celery-workers -f --all-containers=true

# Celery Worker na konkretnym node
kubectl logs -l app=celery-workers -f --field-selector spec.nodeName=<node-name>
```

### Status podów

```bash
# Wszystkie pody
kubectl get pods -o wide

# Tylko aplikacja
kubectl get pods -l component=backend

# Tylko infrastructure
kubectl get pods -l component=database,component=message-broker,component=cache
```

## 🔄 Aktualizacja

### Aktualizacja kodu aplikacji

```bash
# Usuń pody (initContainer sklonuje nową wersję przy restarcie)
kubectl delete pod -l component=backend

# Lub wykonaj rolling update
kubectl rollout restart deployment/sync-controller
kubectl rollout restart deployment/rest-api-controller
kubectl rollout restart daemonset/celery-workers
```

### Aktualizacja konfiguracji

```bash
# 1. Zaktualizuj placeholdery
./set.envs.sh --set key=value --dir ./k8s.manifests

# 2. Zastosuj nową konfigurację
kubectl apply -f k8s.manifests/config-env.yml

# 3. Zrestartuj pody aby załadować nową konfigurację
kubectl rollout restart deployment/sync-controller
kubectl rollout restart deployment/rest-api-controller
kubectl rollout restart daemonset/celery-workers
```

## 🧹 Cleanup

```bash
# Usuń wszystkie komponenty aplikacji
kubectl delete -f k8s.manifests/deployment-sync.yml
kubectl delete -f k8s.manifests/deployment-rest-api.yml
kubectl delete -f k8s.manifests/daemonset-celery-workers.yml

# Usuń infrastructure (RabbitMQ, Redis)
# Uwaga: PostgreSQL nie jest usuwany (używamy istniejącego na klastrze)
kubectl delete -f k8s.manifests/deployment-rabbitmq.yml
kubectl delete -f k8s.manifests/deployment-redis.yml

# Usuń services
kubectl delete -f k8s.manifests/services.yml

# Usuń storage (UWAGA: to usunie dane!)
kubectl delete -f k8s.manifests/storage.yml

# Usuń konfigurację
kubectl delete -f k8s.manifests/config-env.yml
```

Lub użyj skryptu:
```bash
cd k8s.manifests
./deploy.sh cleanup
```

## 📝 Uwagi

1. **PostgreSQL**: System używa **istniejącego PostgreSQL** na klastrze pod adresem `postgresql.default.svc.cluster.local`. Nie deployujemy własnego PostgreSQL. Jeśli jednak chcesz deployować własny, użyj pliku `deployment-postgres.optional.yml`.

2. **Storage**: Deployment sync-controller i rest-api-controller używają wspólnego PVC `pvc-pump-bot`. Celery workers używają `emptyDir` (każdy worker ma własny storage).

3. **InitContainers**: Każdy deployment aplikacyjny używa initContainers do:
   - Usunięcia starych plików
   - Sklonowania repozytorium
   - Instalacji tox i zależności

4. **Resources**: Limity zasobów są ustawione jako przykłady - dostosuj je do swoich potrzeb.

5. **NodePort**: REST API i RabbitMQ Management UI są dostępne przez NodePort. W produkcji rozważ użycie Ingress.

6. **Secrets**: Pamiętaj aby **NIGDY** nie commitować config-env.yml z wypełnionymi placeholderami do git!

## 🔐 Bezpieczeństwo

1. **Secrets**: Wszystkie wrażliwe dane (API keys, hasła) są przechowywane w Kubernetes Secret.

2. **Network Policies**: Rozważ dodanie Network Policies aby ograniczyć komunikację między podami.

3. **RBAC**: Skonfiguruj odpowiednie role i service accounts.

4. **Backup**: Regularnie backupuj dane z istniejącego PostgreSQL na klastrze zgodnie z polityką backupu klastra.

## 📚 Dodatkowe zasoby

- [Tox environments](../tox.ini) - definicje wszystkich tox environments
- [Docker Compose](../docker.compose.sh) - alternatywne wdrożenie lokalne
- [Main Controllers](../main_*.py) - główne punkty wejścia aplikacji

