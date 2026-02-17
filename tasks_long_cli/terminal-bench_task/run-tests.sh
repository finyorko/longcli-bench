#!/usr/bin/env bash
set -euo pipefail

OUT="${OUT:-/app/test_output}"
TEST_DIR="${TEST_DIR:-/tests}"
TB_ROOT="/app/terminal-bench"

mkdir -p "$OUT"

source /opt/pytest-proj/.venv/bin/activate

run_cmd() {
  local name="$1"
  shift
  local out_file="$OUT/${name}.txt"
  local status_file="$OUT/${name}.status"

  set +e
  "$@" > "$out_file" 2>&1
  echo $? > "$status_file"
  set -e
}

(
  deactivate
  cd /app/terminal-bench
  run_cmd "tb_help" tb --help
)

set +e
# # f2p: pytest-based integration checks (writes f2p_output.txt for the long_cli parser).
uv run pytest -rA "$TEST_DIR/f2p.py" > "$OUT/f2p_output.txt" 2>&1

set -e
# p2p: text scoring (writes p2p_score.json + p2p_output.txt).
uv run pytest -rA "$TEST_DIR/p2p.py" > "$OUT/p2p_output.txt" 2>&1

