#!/usr/bin/env bash
# cfm offline test suite — stdlib unittest, no model calls, no dependency
# beyond python3 + PyYAML (which the plugin already needs).
#
#   tests/run-tests.sh            # everything
#   tests/run-tests.sh -k guard   # unittest -k filter
#   python3 -m unittest tests/test_guard.py -v
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# tests exercise check logic, not the environment gate; check #0 must pass
export CLAUDECODE=1
cd "$ROOT" && exec python3 -m unittest discover -s tests -p 'test_*.py' "$@"
