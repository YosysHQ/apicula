#!/bin/bash
# run_tests.sh - Test runner for gowin_pack C++ packer
#
# Usage: ./tests/run_tests.sh [--chipdb-dir DIR] [--device DEVICE]
#
# These tests exercise functionality identified in the REVIEW.md:
#   - DLLDLY handler (previously unimplemented)
#   - PINCFG validation (previously no-op)
#   - BSRAM with GW5AST-138C (previously missing device check)
#
# Requirements:
#   - Built gowin_pack binary (cmake --build build)
#   - Chipdb files for the target device (set APYCULA_CHIPDB_DIR or --chipdb-dir)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GOWIN_PACK="${PROJECT_DIR}/build/gowin_pack"

CHIPDB_DIR=""
DEVICE="GW1N-9C"
PASSED=0
FAILED=0
SKIPPED=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --chipdb-dir) CHIPDB_DIR="$2"; shift 2 ;;
        --device) DEVICE="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# Check binary exists
if [[ ! -x "$GOWIN_PACK" ]]; then
    echo "ERROR: gowin_pack not found at $GOWIN_PACK"
    echo "Build it first: cmake -B build && cmake --build build"
    exit 1
fi

# Set chipdb env if provided
if [[ -n "$CHIPDB_DIR" ]]; then
    export APYCULA_CHIPDB_DIR="$CHIPDB_DIR"
fi

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

# Helper: run a test case
run_test() {
    local name="$1"
    local json="$2"
    local device="${3:-$DEVICE}"
    local extra_args="${4:-}"
    local expect_stderr="${5:-}"

    printf "  %-40s " "$name"

    local output="$TMPDIR/${name}.fs"
    local stderr_file="$TMPDIR/${name}.stderr"

    if ! $GOWIN_PACK -d "$device" -o "$output" $extra_args "$json" 2>"$stderr_file"; then
        # Check if failure is due to missing chipdb
        if grep -q "Could not find chipdb\|Could not open chipdb\|chipdb" "$stderr_file" 2>/dev/null; then
            echo "SKIP (no chipdb for $device)"
            SKIPPED=$((SKIPPED + 1))
            return
        fi
        echo "FAIL (exit code)"
        cat "$stderr_file" >&2
        FAILED=$((FAILED + 1))
        return
    fi

    # Check expected stderr content if specified
    if [[ -n "$expect_stderr" ]]; then
        if grep -q "$expect_stderr" "$stderr_file" 2>/dev/null; then
            echo "PASS (warning emitted)"
            PASSED=$((PASSED + 1))
            return
        else
            echo "FAIL (expected warning not found: $expect_stderr)"
            echo "  stderr was: $(cat "$stderr_file")"
            FAILED=$((FAILED + 1))
            return
        fi
    fi

    # Check output file was created and is non-empty
    if [[ -s "$output" ]]; then
        echo "PASS"
        PASSED=$((PASSED + 1))
    else
        echo "FAIL (empty output)"
        FAILED=$((FAILED + 1))
    fi
}

echo "=== gowin_pack test suite ==="
echo "Binary: $GOWIN_PACK"
echo "Device: $DEVICE"
echo ""

# --- DLLDLY tests ---
echo "DLLDLY handler tests:"
run_test "dlldly_basic" "$SCRIPT_DIR/dlldly_basic.json"
run_test "dlldly_negative_sign" "$SCRIPT_DIR/dlldly_negative.json"
echo ""

# --- PINCFG validation tests ---
echo "PINCFG validation tests:"
run_test "pincfg_i2c_conflict" "$SCRIPT_DIR/pincfg_i2c.json" "$DEVICE" "" "i2c_as_gpio has conflicting"
run_test "pincfg_i2c_matching" "$SCRIPT_DIR/pincfg_i2c.json" "$DEVICE" "--i2c_as_gpio"
run_test "pincfg_sspi_conflict" "$SCRIPT_DIR/pincfg_sspi.json" "$DEVICE" "" "sspi_as_gpio has conflicting"
run_test "pincfg_sspi_matching" "$SCRIPT_DIR/pincfg_sspi.json" "$DEVICE" "--sspi_as_gpio"
echo ""

# --- BSRAM GW5AST-138C test ---
echo "BSRAM GW5AST-138C tests:"
run_test "bsram_gw5ast138c" "$SCRIPT_DIR/bsram_gw5ast.json" "GW5AST-138C"
echo ""

# --- Summary ---
echo "=== Results ==="
echo "Passed:  $PASSED"
echo "Failed:  $FAILED"
echo "Skipped: $SKIPPED"

if [[ $FAILED -gt 0 ]]; then
    exit 1
fi
exit 0
