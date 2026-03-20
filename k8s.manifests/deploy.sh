#!/bin/bash
#
# Skrypt do deploymentu Trading AI Backend na Kubernetes.
# Manifesty: wszystkie *.yml / *.yaml w tym katalogu (bez *.template.*).
# cleanup / cleanup --yes: kubectl delete -f dla tych plików (sort odwrotnie).
#

set -e  # Exit on error

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "${REPO_ROOT}/.env" ]; then
  # shellcheck disable=SC1090
  set -a
  source "${REPO_ROOT}/.env"
  set +a
fi

# Wszystkie *.yml / *.yaml w tym katalogu poza szablonami (*.template.*); kolejność = sort alfabetyczny
list_manifest_files() {
    find "${SCRIPT_DIR}" -maxdepth 1 -type f \( -name '*.yml' -o -name '*.yaml' \) \
        ! -name '*.template.*' \
        -print | LC_ALL=C sort
}

list_manifest_files_reverse() {
    list_manifest_files | LC_ALL=C sort -r
}

kubectl_delete_manifests_from_list() {
    local n=0
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        log_info "kubectl delete -f $(basename "$f") --ignore-not-found=true"
        kubectl delete -f "$f" --ignore-not-found=true
        n=$((n + 1))
    done
    if [ "$n" -eq 0 ]; then
        log_warning "Brak plików manifestów do usunięcia w ${SCRIPT_DIR}"
    fi
}

# Kolory dla lepszej czytelności
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funkcje pomocnicze
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Sprawdź czy kubectl jest dostępny
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl nie jest zainstalowany lub nie jest w PATH"
        exit 1
    fi
    log_success "kubectl jest dostępny"
}

# Sprawdź połączenie z klastrem
check_cluster_connection() {
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Nie można połączyć się z klastrem Kubernetes"
        exit 1
    fi
    log_success "Połączono z klastrem Kubernetes"
}

# Deploy ConfigMap i Secret (config-env.* wygenerowany z template — nie committowany)
deploy_config() {
    log_info "Deployowanie ConfigMap i Secret (config-env.*)..."
    local found=0
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        case "$(basename "$f")" in
            config-env.yml|config-env.yaml)
                log_info "kubectl apply -f $(basename "$f")"
                kubectl apply -f "$f"
                found=1
                ;;
        esac
    done < <(list_manifest_files)
    if [ "$found" -eq 0 ]; then
        log_warning "Brak config-env.yml / config-env.yaml — uruchom set.envs.sh przed deployem"
    else
        log_success "ConfigMap i Secret zostały wdrożone"
    fi
}

# Deploy Storage
deploy_storage() {
    log_info "Deployowanie Storage (PersistentVolume)..."
    log_info "Storage jest teraz wdrażany razem z aplikacjami"
    log_success "Storage będzie wdrożony z odpowiednimi deploymentami"
}

# Deploy Infrastructure (pliki, których nazwa zawiera rabbitmq lub redis)
deploy_infrastructure() {
    log_info "Deployowanie Infrastructure Services (RabbitMQ, Redis)..."
    log_info "Uwaga: Używamy istniejącego PostgreSQL na klastrze (postgresql.default.svc.cluster.local)"
    
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        b=$(basename "$f")
        case "$b" in
            *rabbitmq*|*redis*)
                log_info "kubectl apply -f $b"
                kubectl apply -f "$f"
                ;;
        esac
    done < <(list_manifest_files)
    
    log_info "Oczekiwanie na gotowość Infrastructure Services..."
    
    # Czekaj na RabbitMQ
    log_info "Czekam na RabbitMQ..."
    kubectl wait --for=condition=ready pod -l app=trading-ai-backend-rabbitmq --timeout=300s || log_warning "Timeout podczas oczekiwania na RabbitMQ"
    
    # Czekaj na Redis
    log_info "Czekam na Redis..."
    kubectl wait --for=condition=ready pod -l app=trading-ai-backend-redis --timeout=300s || log_warning "Timeout podczas oczekiwania na Redis"
    
    log_success "Infrastructure Services są gotowe"
}

# Deploy Application Services — wszystko poza config-env, infrastrukturą mq/redis i services.*
deploy_applications() {
    log_info "Deployowanie Application Services (pozostałe manifesty wg nazw plików)..."
    
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        b=$(basename "$f")
        case "$b" in
            config-env.yml|config-env.yaml) continue ;;
            *rabbitmq*|*redis*) continue ;;
            services.yml|services.yaml) continue ;;
        esac
        log_info "kubectl apply -f $b"
        kubectl apply -f "$f"
    done < <(list_manifest_files)
    
    log_success "Application Services wdrożone (kolejność alfabetyczna — prefiksy 10-, 20- w nazwach plików jeśli zależności tego wymagają)"
}

# Deploy Services (services.yml / services.yaml)
deploy_services() {
    log_info "Deployowanie Services..."
    local found=0
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        case "$(basename "$f")" in
            services.yml|services.yaml)
                log_info "kubectl apply -f $(basename "$f")"
                kubectl apply -f "$f"
                found=1
                ;;
        esac
    done < <(list_manifest_files)
    if [ "$found" -eq 0 ]; then
        log_info "Brak services.yml — pomijam"
    else
        log_success "Services zostały wdrożone"
    fi
}

# Wyświetl status
show_status() {
    log_info "Status wszystkich podów:"
    kubectl get pods -o wide
    
    echo ""
    log_info "Status wszystkich serwisów:"
    kubectl get services
    
    echo ""
    log_info "Status PVC:"
    kubectl get pvc
}

# Wyświetl logi
show_logs() {
    log_info "Dostępne opcje do podglądu logów:"
    echo ""
    echo "  kubectl logs -l app=trading-ai-backend-rest-api-controller -f"
    echo "  kubectl logs -l app=trading-ai-frontend-web -f -c nginx"
    echo "  kubectl logs -l app=trading-ai-backend-celery-workers -f"
    echo "  kubectl logs -l component=backend -f --all-containers=true"
    echo ""
}

# Wyświetl informacje o dostępie
show_access_info() {
    echo ""
    log_info "==================== DOSTĘP DO SERWISÓW ===================="
    echo ""
    
    # Pobierz IP pierwszego node
    NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
    
    log_info "REST API:"
    echo "  Wewnętrzny: http://trading-ai-backend-rest-api-service:9090"
    echo "  Zewnętrzny: http://${NODE_IP}:30090"
    echo "  Health Check: http://${NODE_IP}:30090/health"
    echo "  API Docs: http://${NODE_IP}:30090/docs"
    echo ""

    log_info "Frontend (nginx, ClusterIP + Ingress):"
    echo "  W klastrze: http://trading-ai-frontend-service.default.svc.cluster.local"
    echo "  Publicznie (po DNS + Ingress TLS staging): https://00x097.com"
    echo ""
    
    log_info "RabbitMQ Management UI (tylko ClusterIP - dostęp przez port-forward):"
    echo "  Port Forward: kubectl port-forward svc/trading-ai-backend-rabbitmq-management 15672:15672"
    echo "  URL (po port-forward): http://localhost:15672"
    echo "  User: trading_bot_ai_rabbit"
    echo "  Password: <sprawdź w Secret: kubectl get secret trading-ai-secrets -o jsonpath='{.data.RABBITMQ_PASSWORD}' | base64 -d>"
    echo ""
    
    log_success "==================== DEPLOYMENT ZAKOŃCZONY ===================="
}

# Cleanup (usunięcie zasobów z manifestów w tym katalogu; odwrotna kolejność nazw plików)
cleanup() {
    local auto_confirm="${1:-}"
    log_warning "Usuwanie zasobów Trading AI Backend z manifestów w ${SCRIPT_DIR}..."
    
    if [ "$auto_confirm" != "--yes" ]; then
        read -r -p "Czy na pewno chcesz usunąć wszystkie zasoby? (yes/no): " confirm
        if [ "$confirm" != "yes" ]; then
            log_info "Anulowano cleanup"
            exit 0
        fi
    else
        log_info "Potwierdzenie pominięte (--yes, np. CI)"
    fi
    
    log_info "Uwaga: PostgreSQL na klastrze nie jest częścią tych manifestów"
    log_info "kubectl delete (kolejność odwrotna do sortowania alfabetycznego nazw plików)..."
    kubectl_delete_manifests_from_list < <(list_manifest_files_reverse)

    log_success "Cleanup zakończony"
}

# Help
show_help() {
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  deploy          - Deploy wszystkich komponentów"
    echo "  deploy-config   - Deploy tylko ConfigMap i Secret"
    echo "  deploy-storage  - Deploy tylko Storage"
    echo "  deploy-infra    - Deploy tylko Infrastructure Services"
    echo "  deploy-apps     - Deploy tylko Application Services"
    echo "  deploy-services - Deploy tylko Services"
    echo "  status          - Wyświetl status wszystkich komponentów"
    echo "  logs            - Wyświetl informacje o logach"
    echo "  access          - Wyświetl informacje o dostępie do serwisów"
    echo "  cleanup         - Usuń zasoby ze wszystkich *.yml/*.yaml (bez template); opcjonalnie: cleanup --yes (CI)"
    echo "  help            - Wyświetl tę pomoc"
    echo ""
}

# Main
main() {
    case "${1:-deploy}" in
        deploy)
            log_info "==================== DEPLOYMENT TRADING AI BACKEND ===================="
            check_kubectl
            check_cluster_connection
            deploy_config
            deploy_storage
            deploy_infrastructure
            deploy_applications
            deploy_services
            show_status
            show_logs
            show_access_info
            ;;
        deploy-config)
            check_kubectl
            check_cluster_connection
            deploy_config
            ;;
        deploy-storage)
            check_kubectl
            check_cluster_connection
            deploy_storage
            ;;
        deploy-infra)
            check_kubectl
            check_cluster_connection
            deploy_infrastructure
            ;;
        deploy-apps)
            check_kubectl
            check_cluster_connection
            deploy_applications
            ;;
        deploy-services)
            check_kubectl
            check_cluster_connection
            deploy_services
            ;;
        status)
            check_kubectl
            check_cluster_connection
            show_status
            ;;
        logs)
            show_logs
            ;;
        access)
            check_kubectl
            check_cluster_connection
            show_access_info
            ;;
        cleanup)
            check_kubectl
            check_cluster_connection
            cleanup "${2:-}"
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "Nieznana komenda: $1"
            show_help
            exit 1
            ;;
    esac
}

# Uruchom main
main "$@"

