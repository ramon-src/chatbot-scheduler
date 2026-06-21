#!/bin/bash
# =============================================================================
# SIMPLIFICAPSI - INSTALL SCRIPT
# =============================================================================

set -e  # Exit on any error

echo "📦 SimplificaPsi - Install Script"
echo "=================================="
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
INSTALL_TYPE=${1:-"all"}
PACKAGE=${2:-""}

# =============================================================================
# FUNCTIONS
# =============================================================================
install_uv() {
    print_status "Installing uv..."
    
    if command -v uv &> /dev/null; then
        print_warning "uv is already installed"
        return
    fi
    
    # Install uv
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # Add to PATH
    export PATH="$HOME/.cargo/bin:$PATH"
    
    print_success "uv installed successfully!"
}

install_dependencies() {
    print_status "Installing project dependencies..."
    
    # Install dependencies
    uv sync
    
    print_success "Dependencies installed!"
}

install_dev_dependencies() {
    print_status "Installing development dependencies..."
    
    # Install dev dependencies
    uv sync --dev
    
    print_success "Development dependencies installed!"
}

install_specific_package() {
    if [ -z "$PACKAGE" ]; then
        print_error "Please provide a package name"
        echo "Usage: $0 package <package_name>"
        exit 1
    fi
    
    print_status "Installing package: $PACKAGE"
    uv add "$PACKAGE"
    print_success "Package $PACKAGE installed!"
}

install_dev_package() {
    if [ -z "$PACKAGE" ]; then
        print_error "Please provide a package name"
        echo "Usage: $0 dev-package <package_name>"
        exit 1
    fi
    
    print_status "Installing dev package: $PACKAGE"
    uv add --dev "$PACKAGE"
    print_success "Dev package $PACKAGE installed!"
}

setup_pre_commit() {
    print_status "Setting up pre-commit hooks..."
    uv run pre-commit install
    print_success "Pre-commit hooks installed!"
}

# =============================================================================
# MAIN LOGIC
# =============================================================================
case $INSTALL_TYPE in
    "uv")
        install_uv
        ;;
    "deps")
        install_dependencies
        ;;
    "dev-deps")
        install_dev_dependencies
        ;;
    "all")
        install_uv
        install_dependencies
        install_dev_dependencies
        setup_pre_commit
        ;;
    "package")
        install_specific_package
        ;;
    "dev-package")
        install_dev_package
        ;;
    "pre-commit")
        setup_pre_commit
        ;;
    *)
        print_error "Invalid install type: $INSTALL_TYPE"
        echo ""
        echo "Usage: $0 <install_type> [package_name]"
        echo ""
        echo "Install types:"
        echo "  uv          - Install uv package manager"
        echo "  deps        - Install project dependencies"
        echo "  dev-deps    - Install development dependencies"
        echo "  all         - Install everything (default)"
        echo "  package     - Install specific package"
        echo "  dev-package - Install specific dev package"
        echo "  pre-commit  - Setup pre-commit hooks"
        echo ""
        echo "Examples:"
        echo "  $0 all"
        echo "  $0 package requests"
        echo "  $0 dev-package pytest"
        echo "  $0 pre-commit"
        exit 1
        ;;
esac

print_success "Installation completed! 🎉"
