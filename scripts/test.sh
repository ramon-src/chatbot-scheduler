#!/bin/bash
# =============================================================================
# SIMPLIFICAPSI - TEST SCRIPT
# =============================================================================

set -e  # Exit on any error

echo "🧪 SimplificaPsi - Test Runner"
echo "==============================="
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
TEST_TYPE=${1:-"all"}
COVERAGE=${2:-"false"}
VERBOSE=${3:-"true"}

# =============================================================================
# FUNCTIONS
# =============================================================================
run_unit_tests() {
    print_status "Running unit tests..."
    if [ "$VERBOSE" = "true" ]; then
        uv run pytest tests/unit/ -v
    else
        uv run pytest tests/unit/
    fi
    print_success "Unit tests completed!"
}

run_integration_tests() {
    print_status "Running integration tests..."
    if [ "$VERBOSE" = "true" ]; then
        uv run pytest tests/integration/ -v
    else
        uv run pytest tests/integration/
    fi
    print_success "Integration tests completed!"
}

run_all_tests() {
    print_status "Running all tests..."
    if [ "$COVERAGE" = "true" ]; then
        if [ "$VERBOSE" = "true" ]; then
            uv run pytest tests/ --cov=app --cov-report=html --cov-report=term -v
        else
            uv run pytest tests/ --cov=app --cov-report=html --cov-report=term
        fi
    else
        if [ "$VERBOSE" = "true" ]; then
            uv run pytest tests/ -v
        else
            uv run pytest tests/
        fi
    fi
    print_success "All tests completed!"
}

run_specific_test() {
    local test_file=$1
    print_status "Running specific test: $test_file"
    if [ "$VERBOSE" = "true" ]; then
        uv run pytest "$test_file" -v
    else
        uv run pytest "$test_file"
    fi
    print_success "Specific test completed!"
}

# =============================================================================
# MAIN LOGIC
# =============================================================================
case $TEST_TYPE in
    "unit")
        run_unit_tests
        ;;
    "integration")
        run_integration_tests
        ;;
    "all")
        run_all_tests
        ;;
    "file")
        if [ -z "$2" ]; then
            print_error "Please provide a test file path"
            echo "Usage: $0 file <test_file_path>"
            exit 1
        fi
        run_specific_test "$2"
        ;;
    "watch")
        print_status "Running tests in watch mode..."
        uv run pytest-watch tests/ -v
        ;;
    *)
        print_error "Invalid test type: $TEST_TYPE"
        echo ""
        echo "Usage: $0 <test_type> [coverage] [verbose]"
        echo ""
        echo "Test types:"
        echo "  unit        - Run only unit tests"
        echo "  integration - Run only integration tests"
        echo "  all         - Run all tests (default)"
        echo "  file <path> - Run specific test file"
        echo "  watch       - Run tests in watch mode"
        echo ""
        echo "Options:"
        echo "  coverage    - true/false (default: false)"
        echo "  verbose     - true/false (default: true)"
        echo ""
        echo "Examples:"
        echo "  $0 unit"
        echo "  $0 all true"
        echo "  $0 file tests/unit/test_client.py"
        echo "  $0 watch"
        exit 1
        ;;
esac

# =============================================================================
# COVERAGE REPORT
# =============================================================================
if [ "$COVERAGE" = "true" ]; then
    print_status "Coverage report generated in htmlcov/index.html"
    if command -v open &> /dev/null; then
        print_status "Opening coverage report in browser..."
        open htmlcov/index.html
    elif command -v xdg-open &> /dev/null; then
        print_status "Opening coverage report in browser..."
        xdg-open htmlcov/index.html
    fi
fi

print_success "Test execution completed! 🎉"
