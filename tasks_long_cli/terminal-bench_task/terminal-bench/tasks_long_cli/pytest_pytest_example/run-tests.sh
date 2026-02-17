#!/bin/bash

# uv venv .tbench-testing
source /opt/pytest-proj/.venv/bin/activate
uv pip install pytest==8.4.1

Create Test Directory
mkdir -p /app/test_output

#### f2p pytest
uv run pytest /tests/f2p.py -rA > /app/test_output/f2p_output.txt 2>&1

#### p2p pytest
uv run pytest /tests/p2p.py -rA > /app/test_output/p2p_output.txt 2>&1
