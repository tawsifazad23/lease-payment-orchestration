#!/bin/bash

# Performance Testing Runner Script
# This script runs all performance tests for the Lease Payment Orchestration system

set -e

echo "==== Performance Testing Suite ===="
echo ""

# Check if dependencies are installed
echo "Checking dependencies..."
python3 -c "import pytest; import sqlalchemy; import locust" 2>/dev/null || {
    echo "Error: Required dependencies not installed"
    echo "Run: pip install -r requirements.txt"
    exit 1
}

# Test 1: Benchmarks
echo ""
echo "1. Running Performance Benchmarks..."
echo "   (Measures critical operations against thresholds)"
python3 tests/performance/benchmarks.py

# Test 2: Stress Tests
echo ""
echo "2. Running Stress Tests..."
echo "   (Tests system behavior under extreme load)"
python3 tests/performance/stress_tests.py

# Test 3: Load Tests
echo ""
echo "3. Load Testing Instructions"
echo "   (Requires running services)"
echo ""
echo "   Option A - Interactive UI:"
echo "   $ locust -f tests/load/locustfile.py"
echo ""
echo "   Option B - Headless for 5 minutes with 10 users:"
echo "   $ locust -f tests/load/locustfile.py \\"
echo "       --host=http://localhost:8000 \\"
echo "       --users 10 --spawn-rate 1 --run-time 5m --headless"
echo ""

echo "==== Performance Testing Complete ===="
