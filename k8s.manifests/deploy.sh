#!/bin/bash
#
# Skrypt do deploymentu Trading AI Backend na Kubernetes
# Autor: AI Assistant
# Data: 2025
#

set -e  # Exit on error

source ../.env;

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

# Deploy ConfigMap i Secret
deploy_config() {
    log_info "Deployowanie ConfigMap i Secret..."
    kubectl apply -f config-env.yml
    log_success "ConfigMap i Secret zostały wdrożone"
}

# Deploy Storage
deploy_storage() {
    log_info "Deployowanie Storage (PersistentVolume)..."
    kubectl apply -f storage.yml
    log_success "Storage został wdrożony"
}

# Deploy Infrastructure
deploy_infrastructure() {
    log_info "Deployowanie Infrastructure Services (RabbitMQ, Redis)..."
    log_info "Uwaga: Używamy istniejącego PostgreSQL na klastrze (postgresql.default.svc.cluster.local)"
    
    kubectl apply -f deployment-rabbitmq.yml
    log_success "RabbitMQ został wdrożony"
    
    kubectl apply -f deployment-redis.yml
    log_success "Redis został wdrożony"
    
    log_info "Oczekiwanie na gotowość Infrastructure Services..."
    
    # Czekaj na RabbitMQ
    log_info "Czekam na RabbitMQ..."
    kubectl wait --for=condition=ready pod -l app=rabbitmq --timeout=300s || log_warning "Timeout podczas oczekiwania na RabbitMQ"
    
    # Czekaj na Redis
    log_info "Czekam na Redis..."
    kubectl wait --for=condition=ready pod -l app=redis --timeout=300s || log_warning "Timeout podczas oczekiwania na Redis"
    
    log_success "Infrastructure Services są gotowe"
}

# Deploy Application Services
deploy_applications() {
    log_info "Deployowanie Application Services..."
    
    kubectl apply -f deployment-sync.yml
    log_success "Sync Controller został wdrożony"
    
    kubectl apply -f deployment-rest-api.yml
    log_success "REST API Controller został wdrożony"
    
    kubectl apply -f daemonset-celery-workers.yml
    log_success "Celery Workers zostały wdrożone"
}

# Deploy Services
deploy_services() {
    log_info "Deployowanie Services..."
    kubectl apply -f services.yml
    log_success "Services zostały wdrożone"
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
    echo "  kubectl logs -l app=sync-controller -f"
    echo "  kubectl logs -l app=rest-api-controller -f"
    echo "  kubectl logs -l app=celery-workers -f"
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
    echo "  Wewnętrzny: http://rest-api-service:9090"
    echo "  Zewnętrzny: http://${NODE_IP}:30090"
    echo "  Health Check: http://${NODE_IP}:30090/health"
    echo "  API Docs: http://${NODE_IP}:30090/docs"
    echo ""
    
    log_info "RabbitMQ Management UI:"
    echo "  URL: http://${NODE_IP}:30672"
    echo "  User: trading_bot_ai_rabbit"
    echo "  Password: <sprawdź w Secret: kubectl get secret trading-ai-secrets -o jsonpath='{.data.RABBITMQ_PASSWORD}' | base64 -d>"
    echo ""
    
    log_success "==================== DEPLOYMENT ZAKOŃCZONY ===================="
}

# Cleanup (usunięcie wszystkich zasobów)
cleanup() {
    log_warning "Usuwanie wszystkich zasobów Trading AI Backend..."
    
    read -p "Czy na pewno chcesz usunąć wszystkie zasoby? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        log_info "Anulowano cleanup"
        exit 0
    fi
    
    log_info "Usuwanie Application Services..."
    kubectl delete -f deployment-sync.yml --ignore-not-found=true
    kubectl delete -f deployment-rest-api.yml --ignore-not-found=true
    kubectl delete -f daemonset-celery-workers.yml --ignore-not-found=true
    
    log_info "Usuwanie Infrastructure Services..."
    log_info "Uwaga: PostgreSQL nie jest usuwany (używamy istniejącego PostgreSQL na klastrze)"
    kubectl delete -f deployment-rabbitmq.yml --ignore-not-found=true
    kubectl delete -f deployment-redis.yml --ignore-not-found=true
    
    log_info "Usuwanie Services..."
    kubectl delete -f services.yml --ignore-not-found=true
    
    read -p "Czy usunąć Storage (UWAGA: to usunie wszystkie dane!)? (yes/no): " confirm_storage
    if [ "$confirm_storage" == "yes" ]; then
        log_info "Usuwanie Storage..."
        kubectl delete -f storage.yml --ignore-not-found=true
    fi
    
    log_info "Usuwanie ConfigMap i Secret..."
    kubectl delete -f config-env.yml --ignore-not-found=true
    
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
    echo "  cleanup         - Usuń wszystkie zasoby"
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
            cleanup
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

