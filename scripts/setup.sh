#!/bin/bash
# =============================================================================
# SIMPLIFICAPSI - SETUP SCRIPT
# =============================================================================

set -e  # Exit on any error

echo "🚀 SimplificaPsi - Project Setup"
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

check_command() {
    if ! command -v $1 &> /dev/null; then
        print_error "$1 is not installed. Please install it first."
        exit 1
    fi
}

# =============================================================================
# CHECK REQUIREMENTS
# =============================================================================
print_status "Checking requirements..."

check_command "python3"
check_command "uv"
check_command "docker"
check_command "docker-compose"

print_success "All requirements are installed!"

# =============================================================================
# PYTHON VERSION CHECK
# =============================================================================
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
REQUIRED_VERSION="3.11"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    print_error "Python $REQUIRED_VERSION or higher is required. Found: $PYTHON_VERSION"
    exit 1
fi

print_success "Python version is compatible: $PYTHON_VERSION"

# =============================================================================
# CREATE ENVIRONMENT FILE
# =============================================================================
if [ ! -f .env ]; then
    print_status "Creating .env file from template..."
    cp env.example .env
    print_success ".env file created!"
    print_warning "Please edit .env file with your configuration before running the application."
else
    print_status ".env file already exists, skipping..."
fi

# =============================================================================
# INSTALL DEPENDENCIES
# =============================================================================
print_status "Installing dependencies with uv..."
uv sync
print_success "Dependencies installed!"

# =============================================================================
# SETUP PRE-COMMIT HOOKS
# =============================================================================
print_status "Setting up pre-commit hooks..."
uv run pre-commit install
print_success "Pre-commit hooks installed!"

# =============================================================================
# CREATE LOGS DIRECTORY
# =============================================================================
print_status "Creating logs directory..."
mkdir -p logs
print_success "Logs directory created!"

# =============================================================================
# DOCKER SETUP
# =============================================================================
print_status "Setting up Docker environment..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    print_error "Docker is not running. Please start Docker first."
    exit 1
fi

# Build Docker images
print_status "Building Docker images..."
docker-compose build
print_success "Docker images built!"

# =============================================================================
# DATABASE SETUP
# =============================================================================
print_status "Setting up database..."

# Start database
print_status "Starting PostgreSQL container..."
docker-compose up -d postgres

# Wait for database to be ready
print_status "Waiting for database to be ready..."
sleep 10

# Check if database is ready
until docker-compose exec postgres pg_isready -U simplificapsi -d simplificapsi_dev; do
    print_status "Waiting for database..."
    sleep 2
done

print_success "Database is ready!"

# =============================================================================
# REDIS SETUP
# =============================================================================
print_status "Setting up Redis..."
docker-compose up -d redis

# Wait for Redis to be ready
print_status "Waiting for Redis to be ready..."
sleep 5

# Check if Redis is ready
until docker-compose exec redis redis-cli ping; do
    print_status "Waiting for Redis..."
    sleep 2
done

print_success "Redis is ready!"

# =============================================================================
# RUN MIGRATIONS
# =============================================================================
print_status "Running database migrations..."
uv run alembic upgrade head
print_success "Database migrations completed!"

# =============================================================================
# FINAL SETUP
# =============================================================================
print_status "Running final setup..."

# Create necessary directories
mkdir -p logs
mkdir -p migrations/versions

# Set permissions
chmod +x scripts/*.sh

print_success "Final setup completed!"

# =============================================================================
# COMPLETION MESSAGE
# =============================================================================
echo ""
echo "🎉 Setup completed successfully!"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your configuration"
echo "2. Run 'make dev' to start the development server"
echo "3. Run 'make docker-up' to start all services"
echo "4. Visit http://localhost:8000 to see the API"
echo "5. Visit http://localhost:5050 for pgAdmin (admin@simplificapsi.com / admin123)"
echo "6. Visit http://localhost:8081 for Redis Commander (admin / admin123)"
echo ""
echo "Useful commands:"
echo "- make dev          # Start development server"
echo "- make test         # Run tests"
echo "- make lint         # Run linting"
echo "- make format       # Format code"
echo "- make docker-up    # Start all services"
echo "- make docker-down  # Stop all services"
echo ""
echo "Happy coding! 🚀"
