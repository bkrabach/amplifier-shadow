#!/bin/bash
# Shadow Environment Test Runner
# Runs all shadow environment tests inside the workspace container
#
# Usage:
#   ./run_shadow_tests.sh              # Run all tests
#   ./run_shadow_tests.sh --quick      # Run quick URL rewriting tests only

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHADOW_DIR="$(dirname "$SCRIPT_DIR")"
AMPLIFIER_DEV="$(dirname "$SHADOW_DIR")"

echo "=============================================="
echo "Shadow Environment Test Runner"
echo "=============================================="
echo ""

# Check if shadow environment is running
if ! docker ps --format '{{.Names}}' | grep -q "default-workspace"; then
    echo "❌ Shadow environment not running!"
    echo "   Start it with: ./scripts/init-shadow.sh"
    exit 1
fi

echo "✅ Shadow environment is running"
echo ""

# Publish essential modules to shadow
echo "Publishing modules to shadow Gitea..."
cd "$AMPLIFIER_DEV"

MODULES=(
    "amplifier-module-resolution"
    "amplifier-module-loop-basic"
    "amplifier-module-context-simple"
    "amplifier-module-provider-mock"
    "amplifier-collections"
    "amplifier-collection-recipes"
)

for module in "${MODULES[@]}"; do
    if [ -d "$module" ]; then
        ./amplifier-shadow/scripts/publish-module.sh "$module" 2>&1 | grep -E "(Published|up-to-date)" || true
    fi
done

echo ""
echo "Installing dependencies in workspace..."

# Install amplifier-module-resolution from shadow
docker compose -f "$SHADOW_DIR/templates/docker-compose.yaml" exec -T workspace bash -c '
    uv pip install --system --quiet --force-reinstall \
        "git+http://gitea:3000/amplifier/amplifier-module-resolution.git@main" 2>/dev/null
'

echo ""
echo "=============================================="
echo "Running Shadow Tests"
echo "=============================================="
echo ""

# Run tests
FAILED=0

# Phase 0.4: Profile Loading Tests
echo "--- Phase 0.4: Profile Loading Tests ---"
if docker compose -f "$SHADOW_DIR/templates/docker-compose.yaml" exec -T workspace \
    python3 /workspace/amplifier-shadow/tests/test_profile_loading.py; then
    echo ""
else
    echo "❌ Phase 0.4 tests failed"
    FAILED=1
fi

# Phase 0.5: Collection Tests
echo ""
echo "--- Phase 0.5: Collection Tests ---"
if docker compose -f "$SHADOW_DIR/templates/docker-compose.yaml" exec -T workspace \
    python3 /workspace/amplifier-shadow/tests/test_collection_install.py; then
    echo ""
else
    echo "❌ Phase 0.5 tests failed"
    FAILED=1
fi

echo "=============================================="
echo "Test Summary"
echo "=============================================="

if [ $FAILED -eq 0 ]; then
    echo "✅ All shadow tests passed!"
    exit 0
else
    echo "❌ Some shadow tests failed"
    exit 1
fi
