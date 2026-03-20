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
- **Frontend (React/CRA)** - Sklonowanie repozytorium i `npm ci` + `npm run build` w initContainerach; statyczne pliki z `build/` serwuje **nginx**
- **Celery Workers** - DaemonSet (1 worker per node)

## 🚀 Quick Start

### 1. Konfiguracja zmiennych środowiskowych

Skrypt `set.envs.sh` generuje pliki konfiguracyjne z wrażliwymi danymi na podstawie template'ów:

**Jak to działa:**
- Szuka plików z wzorcem `*.template.*` (np. `config-env.template.yml`)
- Tworzy nowe pliki bez `.template.` (np. `config-env.yml`)
- Replaceuje placeholdery `<<placeholder>>` wartościami
- Template pozostaje niezmieniony i można go commitować do repo
- Wygenerowane pliki (z secretami) są w `.gitignore`

```bash
cd /home/tbs093a/Projects/trading.ai.backend;

source .env;

./set.envs.sh \
  --set trading.ai.backend.repo.url=$REPO_URL \
  --set trading.ai.backend.repo.branch=$REPO_BRANCH \
  --set trading.ai.frontend.repo.url=$FRONTEND_REPO_URL \
  --set trading.ai.frontend.repo.branch=$FRONTEND_REPO_BRANCH \
  --set react.app.api.url=$REACT_APP_API_URL \
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
  --set local.storage.is.enabled=$LOCAL_STORAGE_IS_ENABLED \
  --set local.storage.path=$LOCAL_STORAGE_PATH \
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

**Rezultat:**
```
Processing template: ./k8s.manifests/config-env.template.yml
  Created: ./k8s.manifests/config-env.yml
  ✓ Replaced <<trading.ai.backend.repo.url>> with https://...
  ✓ Replaced <<database.password>> with ******
  ✓ Completed: ./k8s.manifests/config-env.yml
```

### 2. Deploy kolejno wszystkie komponenty

```bash
# 1. ConfigMap i Secret (zmienne środowiskowe)
kubectl apply -f k8s.manifests/config-env.yml

# Frontend z Ingress: **Ingress NGINX** (`ingressClassName: nginx`), rekord DNS `00x097.com` → adres ingressu

# 2. Infrastructure Services (RabbitMQ, Redis)
# Uwaga: PostgreSQL używamy istniejący na klastrze (postgresql.default.svc.cluster.local)
# Storage (PV/PVC) jest teraz wdrażany razem z każdym serwisem
kubectl apply -f k8s.manifests/deployment-rabbitmq.yml
kubectl apply -f k8s.manifests/deployment-redis.yml

# Poczekaj aż infrastructure services będą ready
kubectl wait --for=condition=ready pod -l app=trading-ai-backend-rabbitmq --timeout=300s
kubectl wait --for=condition=ready pod -l app=trading-ai-backend-redis --timeout=300s

# 3. Application Services (każdy ma swój własny PV/PVC)
kubectl apply -f k8s.manifests/deployment-sync.yml
kubectl apply -f k8s.manifests/deployment-rest-api.yml
kubectl apply -f k8s.manifests/deployment-frontend.yml
kubectl apply -f k8s.manifests/ingress-frontend.yml
kubectl apply -f k8s.manifests/daemonset-celery-workers.yml

# 4. Expose Rest api on localhost for CLI
kubectl port-forward service/trading-ai-backend-rest-api-service 9090:9090
```

### 3. Weryfikacja deploymentu

```bash
# Sprawdź status wszystkich podów
kubectl get pods

# Sprawdź logi sync-controller
kubectl logs -l app=trading-ai-backend-sync-controller -f

# Sprawdź logi rest-api-controller
kubectl logs -l app=trading-ai-backend-rest-api-controller -f

# Sprawdź logi celery workers
kubectl logs -l app=trading-ai-backend-celery-workers -f

# Sprawdź services
kubectl get services
```

## 📦 Komponenty

### config-env.template.yml → config-env.yml
Template i wygenerowany plik ConfigMap/Secret z wszystkimi zmiennymi środowiskowymi:
- **config-env.template.yml** - Template z placeholderami `<<key>>` (commitowany do repo)
- **config-env.yml** - Wygenerowany plik z secretami (w .gitignore, NIE commitować!)
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
- Nazwa: `trading-ai-backend-rabbitmq`
- Port AMQP: 5672
- Port Management: 15672 (ClusterIP - dostęp przez port-forward)
- Service: `trading-ai-backend-rabbitmq-service` (AMQP), `trading-ai-backend-rabbitmq-management` (UI)
- PVC: `pvc-trading-ai-backend-rabbitmq` (2Gi)
- Resources: 256Mi-512Mi RAM, 250m-500m CPU

### deployment-redis.yml
Redis 7 Alpine:
- Nazwa: `trading-ai-backend-redis`
- Port: 6379
- Service: `trading-ai-backend-redis-service`
- PVC: `pvc-trading-ai-backend-redis` (1Gi)
- Resources: 128Mi-256Mi RAM, 100m-250m CPU

### deployment-sync.yml
Sync Controller (1 replica):
- Nazwa: `trading-ai-backend-sync-controller`
- Komenda: `tox run -e sync-controller`
- Używa PVC: `pvc-trading-ai-backend-sync` (25Mi)
- Resources: 512Mi-1Gi RAM, 500m-1000m CPU

### deployment-frontend.yml
Frontend (1 replica, POC bez Jenkinsa):
- Nazwa: `trading-ai-frontend-web`
- **Init:** `fix-permissions` → `remove-old-files` → `clone-repo` (jak backend, zmienne `TRADING_AI_FRONTEND_*`) → `npm-install-build`: obraz **`node:24.12.0-bookworm`**, `npm install -g npm@11.6.2`, potem `npm ci` + `npm run build` (init jako root, na końcu `chown` `1000:1000` na `/app`), `REACT_APP_API_URL` z ConfigMap na czas buildu
- **Runtime:** `nginx:alpine` montuje `subPath: build` jako document root; `ConfigMap` `trading-ai-frontend-nginx-config` — `try_files` pod SPA
- PVC: `pvc-trading-ai-frontend` (**2Gi** — repo + `node_modules` + artefakt build)
- PV: hostPath `/k8s/pv/trading-ai-frontend`, afinitacja węzła jak inne PV (domyślnie `k8s.node.001` — dostosuj do klastra)
- Service **ClusterIP** `trading-ai-frontend-service:80` (ruch zewnętrzny przez Ingress)

### ingress-frontend.yml
- **Ingress** host `00x097.com` → `trading-ai-frontend-service:80` (HTTP, bez cert-manager / TLS w repo)
- `ingressClassName: nginx` — dopasuj do swojego Ingress Controllera

**Uwaga:** `REACT_APP_API_URL` musi być adresem **osiągalnym z przeglądarki użytkownika** (np. publiczny URL API z Ingress/NodePort), nie wyłącznie `*.svc.cluster.local`. TLS (np. Let’s Encrypt) możesz dodać osobno w klastrze (własny Issuer / adnotacje na Ingress).

### deployment-rest-api.yml
REST API Controller (1 replica):
- Nazwa: `trading-ai-backend-rest-api-controller`
- Komenda: `tox run -e rest-api-controller`
- Port: 9090 (NodePort 30090)
- Service: `trading-ai-backend-rest-api-service`
- Health checks: `/health`
- Używa PVC: `pvc-trading-ai-backend-rest-api` (25Mi)
- Resources: 512Mi-1Gi RAM, 500m-1000m CPU

### daemonset-celery-workers.yml
Celery Workers (1 worker per node):
- Nazwa: `trading-ai-backend-celery-workers`
- Komenda: `tox run -e rest-api-celery-worker`
- DaemonSet - każdy node otrzyma 1 worker
- Używa hostPath (każdy worker na każdym node ma własny storage)
- Resources: 512Mi-1Gi RAM, 500m-1000m CPU

### services.yml
Serwisy (tylko Redis - reszta jest w odpowiednich plikach deploymentów):
- `trading-ai-backend-redis-service` (ClusterIP:6379)

**Uwaga**: PostgreSQL service nie jest potrzebny - używamy istniejącego `postgresql.default.svc.cluster.local`

## Jenkins (`Jenkinsfile` w katalogu głównym repo)

Pipeline: `checkout scm` → usuwa `k8s.manifests/config-env.yml` → `./set.envs.sh ... --dir ./k8s.manifests` (wartości z **parametrów** builda + **withCredentials**) → `k8s.manifests/deploy.sh deploy` (gdy zaznaczono **DEPLOY**).

**Secret text** (IDs — nagłówek `Jenkinsfile`): OpenAI, CryptoPanic, GNews, CoinDesk, MinIO access/secret, Redis. **Username with password:** `trading-ai-database-credentials`, `trading-ai-rabbitmq-credentials` (user/hasło do `database.*` i `rabbitmq.*` w `config-env`). Pozostałe: `usernamePassword` (Git, Telegram, KuCoin, MEXC).

Parametry domyślne odpowiadają typowej konfiguracji klastra / MinIO; ścieżki Git w parametrach **bez** `https://` — token składa Jenkins z credentialu `git-gitea-tbs093a`.

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
CELERY_BROKER_URL="pyamqp://${RABBITMQ_USER}:${RABBITMQ_PASSWORD}@trading-ai-backend-rabbitmq-service:${RABBITMQ_PORT}//"
CELERY_RESULT_BACKEND="redis://:${REDIS_PASSWORD}@trading-ai-backend-redis-service:${REDIS_PORT}/0"
```

## 🌐 Dostęp do serwisów

### REST API
```bash
# Z wewnątrz klastra
http://trading-ai-backend-rest-api-service:9090

# Z zewnątrz (NodePort)
http://<NODE_IP>:30090
```

### Frontend
```bash
# Z wewnątrz klastra
http://trading-ai-frontend-service.default.svc.cluster.local

# Z internetu (po DNS + Ingress HTTP)
http://00x097.com

kubectl get ingress -n default
```

### RabbitMQ Management UI
```bash
# Port Forward (ClusterIP)
kubectl port-forward svc/trading-ai-backend-rabbitmq-management 15672:15672

# Po port-forward
http://localhost:15672

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
kubectl logs -l app=trading-ai-backend-sync-controller -f

# REST API
kubectl logs -l app=trading-ai-backend-rest-api-controller -f

# Celery Workers (wszystkie)
kubectl logs -l app=trading-ai-backend-celery-workers -f --all-containers=true

# Celery Worker na konkretnym node
kubectl logs -l app=trading-ai-backend-celery-workers -f --field-selector spec.nodeName=<node-name>
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
kubectl rollout restart deployment/trading-ai-backend-sync-controller
kubectl rollout restart deployment/trading-ai-backend-rest-api-controller
kubectl rollout restart deployment/trading-ai-frontend-web
kubectl rollout restart daemonset/trading-ai-backend-celery-workers
```

### Aktualizacja konfiguracji

```bash
# 1. Edytuj wartości w .env lub eksportuj nowe zmienne

# 2. Wygeneruj nowy config-env.yml z template
./set.envs.sh --set key=value --dir ./k8s.manifests

# 3. Zastosuj nową konfigurację
kubectl apply -f k8s.manifests/config-env.yml

# 4. Zrestartuj pody aby załadować nową konfigurację
kubectl rollout restart deployment/trading-ai-backend-sync-controller
kubectl rollout restart deployment/trading-ai-backend-rest-api-controller
kubectl rollout restart deployment/trading-ai-frontend-web
kubectl rollout restart daemonset/trading-ai-backend-celery-workers
```

## 🧹 Cleanup

```bash
# Usuń wszystkie komponenty aplikacji
kubectl delete -f k8s.manifests/deployment-sync.yml
kubectl delete -f k8s.manifests/deployment-rest-api.yml
kubectl delete -f k8s.manifests/ingress-frontend.yml
kubectl delete -f k8s.manifests/deployment-frontend.yml
kubectl delete -f k8s.manifests/daemonset-celery-workers.yml

# Usuń infrastructure (RabbitMQ, Redis)
# Uwaga: PostgreSQL nie jest usuwany (używamy istniejącego na klastrze)
kubectl delete -f k8s.manifests/deployment-rabbitmq.yml
kubectl delete -f k8s.manifests/deployment-redis.yml

# Usuń konfigurację
kubectl delete -f k8s.manifests/config-env.yml

# Uwaga: Storage (PV/PVC) jest automatycznie usuwany razem z aplikacjami
```

Lub użyj skryptu:
```bash
cd k8s.manifests
./deploy.sh cleanup
```

## 📝 Uwagi

1. **PostgreSQL**: System używa **istniejącego PostgreSQL** na klastrze pod adresem `postgresql.default.svc.cluster.local`. Nie deployujemy własnego PostgreSQL. Jeśli jednak chcesz deployować własny, użyj pliku `deployment-postgres.optional.yml`.

2. **Storage**: Każdy komponent ma swój własny PV/PVC (25Mi dla aplikacji):
   - REST API: `pvc-trading-ai-backend-rest-api` (25Mi)
   - Sync Controller: `pvc-trading-ai-backend-sync` (25Mi)
   - Celery Workers: używają `hostPath` (każdy worker na każdym node ma własny storage)
   - RabbitMQ: `pvc-trading-ai-backend-rabbitmq` (2Gi)
   - Redis: `pvc-trading-ai-backend-redis` (1Gi)

3. **InitContainers**: Każdy deployment aplikacyjny używa initContainers do:
   - Usunięcia starych plików
   - Sklonowania repozytorium
   - Instalacji tox i zależności

4. **Resources**: Limity zasobów są ustawione jako przykłady - dostosuj je do swoich potrzeb.

5. **Nazewnictwo**: Wszystkie obiekty mają prefix `trading-ai-backend-` dla łatwej identyfikacji przynależności do ekosystemu.

6. **NodePort / Ingress**: REST API może być wystawione przez NodePort (30090) — zależnie od manifestu. Frontend: **ClusterIP** + **Ingress** HTTP na `00x097.com`. RabbitMQ Management: ClusterIP (port-forward).

7. **Template Files**: 
   - Commituj do repo: `*.template.*` (z placeholderami)
   - NIE commituj: `config-env.yml` (`.gitignore`)

## 🔐 Bezpieczeństwo

1. **Secrets**: Wszystkie wrażliwe dane (API keys, hasła) są przechowywane w Kubernetes Secret.

2. **Network Policies**: Rozważ dodanie Network Policies aby ograniczyć komunikację między podami.

3. **RBAC**: Skonfiguruj odpowiednie role i service accounts.

4. **Backup**: Regularnie backupuj dane z istniejącego PostgreSQL na klastrze zgodnie z polityką backupu klastra.

## 📚 Dodatkowe zasoby

- [Tox environments](../tox.ini) - definicje wszystkich tox environments
- [Docker Compose](../docker.compose.sh) - alternatywne wdrożenie lokalne
- [Main Controllers](../main_*.py) - główne punkty wejścia aplikacji

