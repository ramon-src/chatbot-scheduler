#!/bin/bash
# =============================================================================
# SIMPLIFICAPSI - DEPLOY SCRIPT
# =============================================================================

set -e  # Exit on any error

echo "🚀 SimplificaPsi - Deploy Script"
echo "================================="
echo ""

# =============================================================================
# COLORS
# =============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# FUNCTIONS
# =============================================================================
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# =============================================================================
# VARIABLES
# =============================================================================
ENVIRONMENT=${1:-"production"}
BACKUP=${2:-"true"}
MIGRATE=${3:-"true"}

# =============================================================================
# FUNCTIONS
# =============================================================================
check_environment() {
    print_status "Checking environment variables..."
    
    if [ ! -f .env ]; then
        print_error ".env file not found!"
        exit 1
    fi
    
    # Check required environment variables
    source .env
    
    required_vars=(
        "DATABASE_URL"
        "REDIS_URL"
        "OPENAI_API_KEY"
        "SECRET_KEY"
        "JWT_SECRET_KEY"
    )
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            print_error "Required environment variable $var is not set!"
            exit 1
        fi
    done
    
    print_success "Environment variables are valid!"
}

backup_database() {
    if [ "$BACKUP" = "true" ]; then
        print_status "Creating database backup..."
        
        # Create backup directory
        mkdir -p backups
        BACKUP_FILE="backups/backup_$(date +%Y%m%d_%H%M%S).sql"
        
        # Create backup
        docker-compose exec -T postgres pg_dump -U simplificapsi simplificapsi_prod > "$BACKUP_FILE"
        
        print_success "Database backup created: $BACKUP_FILE"
    else
        print_warning "Skipping database backup..."
    fi
}

run_migrations() {
    if [ "$MIGRATE" = "true" ]; then
        print_status "Running database migrations..."
        uv run alembic upgrade head
        print_success "Database migrations completed!"
    else
        print_warning "Skipping database migrations..."
    fi
}

deploy_application() {
    print_status "Deploying application..."
    
    # Build production image
    print_status "Building production Docker image..."
    docker-compose -f docker-compose.prod.yml build
    
    # Deploy with production compose
    print_status "Starting production services..."
    docker-compose -f docker-compose.prod.yml up -d
    
    print_success "Application deployed!"
}

health_check() {
    print_status "Performing health check..."
    
    # Wait for services to be ready
    sleep 30
    
    # Check if application is responding
    if curl -f http://localhost:8000/health > /dev/null 2>&1; then
        print_success "Application is healthy!"
    else
        print_error "Application health check failed!"
        exit 1
    fi
}

cleanup() {
    print_status "Cleaning up old images..."
    
    # Remove unused images
    docker image prune -f
    
    # Remove old backups (keep last 10)
    if [ -d "backups" ]; then
        cd backups
        ls -t | tail -n +11 | xargs -r rm
        cd ..
    fi
    
    print_success "Cleanup completed!"
}

# =============================================================================
# MAIN DEPLOYMENT FLOW
# =============================================================================
print_status "Starting deployment process..."

# Check environment
check_environment

# Backup database
backup_database

# Run migrations
run_migrations

# Deploy application
deploy_application

# Health check
health_check

# Cleanup
cleanup

# =============================================================================
# COMPLETION MESSAGE
# =============================================================================
echo ""
echo "🎉 Deployment completed successfully!"
echo "===================================="
echo ""
echo "Application is running at:"
echo "- API: http://localhost:8000"
echo "- Health: http://localhost:8000/health"
echo "- Docs: http://localhost:8000/docs"
echo ""
echo "Useful commands:"
echo "- docker-compose -f docker-compose.prod.yml logs -f  # View logs"
echo "- docker-compose -f docker-compose.prod.yml ps       # Check status"
echo "- docker-compose -f docker-compose.prod.yml down     # Stop services"
echo ""
echo "Deployment successful! 🚀"
