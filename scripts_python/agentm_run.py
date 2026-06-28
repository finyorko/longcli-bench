#!/usr/bin/env python3
"""Run longcli-bench tasks with AgentM as the agent.

Usage:
    # Single task
    LLM_BASE_URL="http://localhost:8088/v1" LLM_API_KEY="..." \
    python scripts_python/agentm_run.py \
        --model doubao-seed-2-0-pro-260215 \
        --task-id 61810_cow \
        --tasks-dir tasks_long_cli \
        --output-path runs_agentm \
        --n-attempts 1 \
        --give-test-output 3

    # Batch (all longcli tasks)
    python scripts_python/agentm_run.py \
        --model doubao-seed-2-0-pro-260215 \
        --tasks-dir tasks_long_cli \
        --output-path runs_agentm \
        --n-attempts 1

Aggregation:
    python scripts_python/longcli_aggregate_results.py \
        --input-dirs runs_agentm \
        --tasks-dir tasks_long_cli \
        --output-json agentm_summary.json \
        --output-csv agentm_summary.csv
"""

from __future__ import annotations

import argparse
import subprocess
import sys


AGENT_IMPORT_PATH = (
    "terminal_bench.agents.installed_agents.agentm.agentm_agent:AgentMAgent"
)

DEFAULT_TASKS = [
    "61810_cow",
    "61810_fs",
    "61810_lock",
    "61810_mmap",
    "61810_net",
    "61810_pgtbl",
    "61810_syscall",
    "61810_thread",
    "61810_traps",
    "61810_util",
    "ap1400_2_hw26",
    "ap1400_2_hw35",
    "cmu15_445_p0",
    "cmu15_445_p1",
    "cmu15_445_p2",
    "cs61_fa24_ants",
    "cs61_fa24_cats",
    "cs61_fa24_hog",
    "cs61_fa24_hw08",
    "cs61_fa24_scheme",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, help="Model name for AgentM")
    parser.add_argument("--task-id", nargs="*", default=None, help="Specific task IDs (default: all 20)")
    parser.add_argument("--tasks-dir", default="tasks_long_cli", help="Task directory")
    parser.add_argument("--output-path", default="runs_agentm", help="Output directory")
    parser.add_argument("--run-id", default=None, help="Run ID (default: agentm-<model>)")
    parser.add_argument("--n-attempts", type=int, default=1, help="Number of attempts per task")
    parser.add_argument("--give-test-output", type=int, default=0, help="Self-correction turns")
    parser.add_argument("--n-concurrent-trials", type=int, default=1, help="Concurrent tasks")
    parser.add_argument("--on-existing", choices=["skip", "overwrite", "error"], default="skip")
    args = parser.parse_args()

    task_ids = args.task_id or DEFAULT_TASKS
    run_id = args.run_id or f"agentm-{args.model.split('/')[-1]}"

    for task_id in task_ids:
        cmd = [
            "uv", "run", "tb", "run",
            "--agent-import-path", AGENT_IMPORT_PATH,
            "--model", args.model,
            "--task-id", task_id,
            "--dataset-path", args.tasks_dir,
            "--run-id", run_id,
            "--n-attempts", str(args.n_attempts),
        ]
        if args.give_test_output:
            cmd.extend(["--give-test-output", str(args.give_test_output)])

        print(f"\n{'='*60}")
        print(f"Running: {task_id}")
        print(f"{'='*60}")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"WARNING: task {task_id} exited with code {result.returncode}")


if __name__ == "__main__":
    main()
