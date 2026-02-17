"""Batch runner for terminal-bench long_cli tasks.

Example:
    python scripts_python/run_long_cli_batch.py \
        --agent-name codex \
        --model-name gpt-5.1-codex-max \
        --task-id 61810_cow 61810_fs 61810_lock \
        --tasks-dir tasks_long_cli \
        --output-path runs_long_cli \
        --on-existing skip
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import shlex
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Iterable


def _slug(value: str) -> str:
    """Make strings safe for file/directory names."""
    return (
        value.replace("/", "-")
        .replace("\\", "-")
        .replace(" ", "_")
        .replace(":", "-")
    )


def _normalize_name(value: str) -> str:
    """Use the last path segment if the name contains '/'; then slug."""
    return _slug(value.rsplit("/", 1)[-1] if "/" in value else value)


def parse_exp_setting(raw: str) -> tuple[int, int]:
    """Parse experiment setting strings like '1,3' or '1:3'."""
    for sep in (",", ":"):
        if sep in raw:
            left, right = raw.split(sep, 1)
            break
    else:
        raise argparse.ArgumentTypeError("Use '<n_attempts>,<test_turn>' format.")

    try:
        return int(left), int(right)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("n_attempts and test_turn must be integers.") from exc


def parse_agent_model_pair(raw: str) -> tuple[str, str]:
    """Parse agent/model pair strings like 'agent,model' or 'agent:model'."""
    for sep in (",", ":"):
        if sep in raw:
            left, right = raw.split(sep, 1)
            break
    else:
        raise argparse.ArgumentTypeError("Use '<agent><,|:><model>' format.")

    left = left.strip()
    right = right.strip()
    if not left or not right:
        raise argparse.ArgumentTypeError("Both agent and model are required in a pair.")
    return left, right


def parse_env_var(raw: str) -> tuple[str, str]:
    """Parse KEY=VALUE env override strings."""
    if "=" not in raw:
        raise argparse.ArgumentTypeError("Env overrides must look like KEY=VALUE.")
    key, val = raw.split("=", 1)
    return key.strip(), val


def parse_parallel_list(raw: str) -> list[str]:
    """Parse comma/space separated parallel dimensions."""
    allowed = {"agent_model_pairs", "task_ids", "exp_settings"}
    parts = [p.strip() for p in raw.replace(",", " ").split() if p.strip()]
    if not parts:
        return []
    for p in parts:
        if p not in allowed:
            raise argparse.ArgumentTypeError(f"Unknown parallel dimension: {p}")
    return parts


def build_command(
    agent_name: str,
    model_name: str,
    task_id: str,
    tasks_dir: Path,
    output_path: Path,
    run_id: str,
    n_attempts: int,
    test_turn: int,
) -> list[str]:
    """Construct the tb run command."""
    return [
        "tb",
        "run",
        "--agent",
        agent_name,
        "--model",
        model_name,
        "--task-id",
        task_id,
        "--dataset-path",
        str(tasks_dir),
        "--output-path",
        str(output_path),
        "--run-id",
        run_id,
        "--n-attempts",
        str(n_attempts),
        "--give-test-output",
        str(test_turn),
    ]


def run_batch(
    task_ids: Iterable[str],
    tasks_dir: Path,
    output_path: Path,
    exp_settings: list[tuple[int, int]],
    on_existing: str,
    env_overrides: dict[str, str] | None = None,
    agent_model_pairs: list[tuple[str, str]] | None = None,
    parallel_dimensions: list[str] | None = None,
    max_workers: int | None = None,
    mode: str = "run",
    script_path: Path | None = None,
) -> None:
    output_path.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if env_overrides:
        env.update({k: str(v) for k, v in env_overrides.items()})

    if not agent_model_pairs:
        raise ValueError("agent_model_pairs is required.")
    pairs = agent_model_pairs
    parallel_dims = list(parallel_dimensions or [])

    run_lock = threading.Lock()

    def run_single(agent: str, model: str, task_id: str, n_attempts: int, test_turn: int) -> int:
        run_id = f"{_normalize_name(agent)}_{_normalize_name(model)}_{_slug(task_id)}_{n_attempts}_{test_turn}"
        run_dir = output_path / run_id

        with run_lock:
            if run_dir.exists():
                if on_existing == "skip":
                    print(f"[skip] {task_id} {run_id} (exists at {run_dir})")
                    return 0
                if on_existing == "overwrite":
                    print(f"[rm] removing existing run dir: {run_dir}")
                    shutil.rmtree(run_dir)
                else:
                    raise ValueError(f"Unknown on_existing mode: {on_existing}")

        cmd = build_command(
            agent,
            model,
            task_id,
            tasks_dir,
            output_path,
            run_id,
            n_attempts,
            test_turn,
        )

        print(f"[run] {task_id} {run_id}")
        print(f"      {shlex.join(cmd)}")
        try:
            subprocess.run(cmd, env=env, check=True)
        except subprocess.CalledProcessError as exc:
            print(f"[error] command failed with code {exc.returncode}")
            return exc.returncode
        return 0

    def run_group(combos: Iterable[tuple[str, str, str, tuple[int, int]]]) -> int:
        for task_id, agent, model, (n_attempts, test_turn) in combos:
            code = run_single(agent, model, task_id, n_attempts, test_turn)
            if code:
                return code
        return 0

    def execute_parallel(combos: list[tuple[str, str, str, tuple[int, int]]]) -> int:
        worker_count = max(1, max_workers or (os.cpu_count() or 4))
        errors: list[int] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(run_single, agent, model, task_id, n_attempts, test_turn)
                for task_id, agent, model, (n_attempts, test_turn) in combos
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    code = future.result()
                    if code:
                        errors.append(code)
                except Exception as exc:
                    print(f"[error] worker crashed: {exc}")
                    errors.append(1)
        return errors[0] if errors else 0

    def submit_groups(groups: list[tuple[tuple, list[tuple[str, str, str, tuple[int, int]]]]]) -> int:
        do_parallel = bool(parallel_dims)
        if not do_parallel:
            for _, combos in groups:
                for task_id, agent, model, (n_attempts, test_turn) in combos:
                    code = run_single(agent, model, task_id, n_attempts, test_turn)
                    if code:
                        return code
            return 0

        for _, combo_list in groups:
            code = run_group(combo_list) if len(combo_list) == 1 else execute_parallel(combo_list)
            if code:
                return code
        return 0

    # Build scheduling groups based on the chosen dimension.
    combos_all: list[tuple[str, str, str, tuple[int, int]]] = []
    for agent, model in pairs:
        for task_id in task_ids:
            for exp in exp_settings:
                combos_all.append((task_id, agent, model, exp))

    all_dims = ["agent_model_pairs", "task_ids", "exp_settings"]
    sequential_dims = [d for d in all_dims if d not in parallel_dims]

    groups: list[tuple[tuple, list[tuple[str, str, str, tuple[int, int]]]]] = []
    groups_dict: dict[tuple, list[tuple[str, str, str, tuple[int, int]]]] = {}
    for task_id, agent, model, exp in combos_all:
        key_parts = []
        for dim in sequential_dims:
            if dim == "agent_model_pairs":
                key_parts.append(("agent_model_pairs", (agent, model)))
            elif dim == "task_ids":
                key_parts.append(("task_ids", task_id))
            elif dim == "exp_settings":
                key_parts.append(("exp_settings", exp))
        key = tuple(key_parts)
        groups_dict.setdefault(key, []).append((task_id, agent, model, exp))
    if not groups_dict:
        groups_dict[tuple()] = combos_all
    groups = [(k, v) for k, v in groups_dict.items()]

    if mode == "expect":
        script_target = script_path or Path("run_long_cli_batches.sh")
        script_target = Path(script_target)
        script_target.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = ["#!/usr/bin/env bash", "set -e", ""]
        lines.append(f"# EXPECT MODE: Only contains commands that have not been executed | Output directory: {output_path}")
        unrun_count = 0  # Number of Unexecuted Tasks

        for idx, (key, combos) in enumerate(groups, start=1):
            # Filter tasks that have not been executed under the current group
            unrun_combos = []
            for combo in combos:
                task_id, agent, model, (n_attempts, test_turn) = combo
                # Generate a unique run_id for task generation, match output directory
                run_id = f"{_normalize_name(agent)}_{_normalize_name(model)}_{_slug(task_id)}_{n_attempts}_{test_turn}"
                run_dir = output_path / run_id
                # Tasks that only retain output directories that do not exist
                if not run_dir.exists():
                    unrun_combos.append(combo)
                    unrun_count += 1

            if not unrun_combos:
                continue  # No pending tasks, skip the current group

            # Generate Group Description
            desc_parts = []
            if key:
                for dim, val in key:
                    if dim == "agent_model_pairs":
                        desc_parts.append(f"agent={val[0]}, model={val[1]}")
                    elif dim == "task_ids":
                        desc_parts.append(f"task_id={val}")
                    elif dim == "exp_settings":
                        desc_parts.append(f"exp=n_attempts:{val[0]},test_turn:{val[1]}")
            else:
                desc_parts.append("no grouping (all selected dimensions parallel)" if parallel_dims else "no parallel dimensions")
            lines.append(f"# batch {idx}: " + "; ".join(desc_parts) + f" | Number of unexecuted tasks: {len(unrun_combos)}")

            # Build commands for unexecuted tasks and write scripts.
            for task_id, agent, model, (n_attempts, test_turn) in unrun_combos:
                run_id = f"{_normalize_name(agent)}_{_normalize_name(model)}_{_slug(task_id)}_{n_attempts}_{test_turn}"
                cmd = build_command(agent, model, task_id, tasks_dir, output_path, run_id, n_attempts, test_turn)
                # Concatenate environment variable prefix
                env_prefix = [f"{k}={shlex.quote(str(v))}" for k, v in env_overrides.items()] if env_overrides else []
                lines.append(" ".join(env_prefix + [shlex.join(cmd)]).strip())
            lines.append("")

        # Write a script and add execution permissions
        script_target.write_text("\n".join(lines))
        try:
            os.chmod(script_target, 0o755)
        except PermissionError:
            print(f"[warn] No permission to add execute permission for {script_target}, you can manually execute chmod +x {script_target}")
        # Output statistical information
        total_count = len(combos_all)
        run_count = total_count - unrun_count
        print(f"[expect] Statistics: Total task count={total_count} | Executed={run_count} | Unexecuted={unrun_count}")
        print(f"[expect] Unexecuted task command {script_target.absolute()}")
        if unrun_count == 0:
            print(f"[expect] Tip: All tasks have been completed, the script is blank")
        return
    # ----------------------------------------------------------------------------

    if mode == "script":
        script_target = script_path or Path("run_long_cli_batches.sh")
        script_target = Path(script_target)
        script_target.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = ["#!/usr/bin/env bash", "set -e", ""]
        lines.append(f"# parallel dimensions: {', '.join(parallel_dims) if parallel_dims else 'none'}")

        for idx, (key, combos) in enumerate(groups, start=1):
            desc_parts = []
            if key:
                for dim, val in key:
                    if dim == "agent_model_pairs":
                        desc_parts.append(f"agent={val[0]}, model={val[1]}")
                    elif dim == "task_ids":
                        desc_parts.append(f"task_id={val}")
                    elif dim == "exp_settings":
                        desc_parts.append(f"exp=n_attempts:{val[0]},test_turn:{val[1]}")
            else:
                desc_parts.append("no grouping (all selected dimensions parallel)" if parallel_dims else "no parallel dimensions")
            lines.append(f"# batch {idx}: " + "; ".join(desc_parts))

            for task_id, agent, model, (n_attempts, test_turn) in combos:
                cmd = build_command(
                    agent,
                    model,
                    task_id,
                    tasks_dir,
                    output_path,
                    f"{_normalize_name(agent)}_{_normalize_name(model)}_{_slug(task_id)}_{n_attempts}_{test_turn}",
                    n_attempts,
                    test_turn,
                )
                env_prefix = [f"{k}={shlex.quote(str(v))}" for k, v in env_overrides.items()] if env_overrides else []
                lines.append(" ".join(env_prefix + [shlex.join(cmd)]).strip())
            lines.append("")

        script_target.write_text("\n".join(lines))
        try:
            os.chmod(script_target, 0o755)
        except PermissionError:
            pass
        print(f"[script] wrote {script_target} with {len(groups)} batches")
        return

    exit_code = submit_groups(groups)
    if exit_code:
        sys.exit(exit_code)


def main(argv: list[str] | None = None) -> None:
    # Set agent-model pairs
    default_agent_model_pairs = [
        # Such as ("codex", "gpt-5.3-codex"),
        ("codex", "gpt-5.3-codex"),
        ("codex", "gpt-5.2-codex"), 
        # ("codex", "gpt-5.2"),
        ("codex", "gpt-5.1-codex-max"),
        ("claude-code", "claude-opus-4-5-20251101"),
        ("claude-code", "claude-opus-4-6"),
        ("claude-code", "claude-sonnet-4-5-20250929"),
    ]
    ## example
    # default_agent_model_pairs = [
    #     ("codex", "gpt-5.3-codex"),
    #     ("codex", "gpt-5.2-codex"), 
    # ]
    
    # tasks
    default_task_ids = [
        #### longcli-bench tasks
        "61810_cow",
        "61810_fs",
        "61810_lock",
        "61810_mmap",
        "61810_net",
        "61810_pgtbl",
        "61810_syscall",
        "61810_thread",
        "61810_traps",
        "cs61_fa24_cats",
        "cs61_fa24_hog",
        "cs61_fa24_hw08",
        "cs61_fa24_scheme",
        "cs61_fa24_ants",
        "terminal-bench_task",
        "ap1400_2_hw26",
        "ap1400_2_hw35",
        "cmu15_445_p0",
        "cmu15_445_p1",
        "cmu15_445_p2",
        #### example task
        # "pytest_pytest_example",
    ]   
    
    # tasks dir
    default_tasks_dir = Path("tasks_long_cli")
    # Test result output directory
    default_output_path = Path("runs_long_cli")
    
    # Experiment setup, the first is how many attempts to run, the second is how many rounds of dialogue
    default_exp_settings = [
        # (1, 1),
        (1, 3),
        (3, 1)
    ]
    
    # Skipped by default if a task has been run
    default_on_existing = "skip"
    # Re-run the experiments that have been run, covering the original
    # default_on_existing = "overwrite"
    
    # Set environment variable
    default_env_overrides = {
        "TB_SAVE_APP_RESULT": "1",
        # "TB_SKIP_AGENT": "1",
        # "ANTHROPIC_API_KEY": "<your-key>",
    }
    # Set concurrency
    default_parallel_dimensions = [
        "agent_model_pairs",
        "task_ids",
        # "exp_settings",
    ]
    
    # Concurrent number
    default_max_workers = 1
    
    
    ## run the task
    default_mode = "run"
    ## output all the tasks in default_script_path
    # default_mode = "script"
    ## Only output the unrun tasks, output as default_script_path
    # default_mode = "expect"
    
    # If default_mode = "script/expect", save the command as default_script_path
    default_script_path = Path("run_long_cli_batches.sh")


    parser = argparse.ArgumentParser(description="Batch runner for long_cli tasks.")
    parser.add_argument("--agent-model-pair", dest="agent_model_pairs", action="append", type=parse_agent_model_pair,
                        help="Agent/model pair in 'agent,model' or 'agent:model' format (can repeat). If omitted, defaults list is used.")
    parser.add_argument("--task-id", dest="task_ids", nargs="*", default=default_task_ids,
                        help=f"One or more task IDs to run (default: {', '.join(default_task_ids)}).")
    parser.add_argument("--tasks-dir", default=default_tasks_dir, type=Path,
                        help=f"Dataset path passed to --dataset-path (default: {default_tasks_dir}).")
    parser.add_argument("--output-path", default=default_output_path, type=Path,
                        help=f"Directory for run outputs (default: {default_output_path}).")
    parser.add_argument("--exp-setting", dest="exp_settings", action="append", type=parse_exp_setting,
                        help=f"Experiment setting in '<n_attempts>,<test_turn>' (can repeat). Default: {default_exp_settings}")
    parser.add_argument("--on-existing", choices=["skip", "overwrite"], default=default_on_existing,
                        help=f"What to do if the run directory already exists (default: {default_on_existing}).")
    parser.add_argument("--env", dest="env_vars", action="append", type=parse_env_var,
                        help="Env override KEY=VALUE (can repeat).")
    parser.add_argument("--parallel-dimension", dest="parallel_dimensions", action="append", type=parse_parallel_list,
                        default=None,
                        help=f"Parallel dimensions (comma/space separated). Choices: agent_model_pairs, task_ids, exp_settings. "
                             f"Default: {', '.join(default_parallel_dimensions) or 'none'}")
    parser.add_argument("--max-workers", type=int, default=default_max_workers,
                        help="Max parallel workers when parallel dimensions are provided (default: cpu_count()).")
    parser.add_argument("--mode", choices=["run", "script", "expect"], default=default_mode,
                        help=f"run: execute commands; script: emit all shell script batches; expect: emit unrun shell script batches (default: {default_mode}).")
    parser.add_argument("--script-path", type=Path, default=default_script_path,
                        help=f"Target shell script when mode=script/expect (default: {default_script_path}).")

    args = parser.parse_args(argv)

    if not args.task_ids:
        parser.error("At least one --task-id is required (default list was emptied).")

    exp_settings = args.exp_settings or default_exp_settings
    env_overrides = dict(default_env_overrides)
    if args.env_vars:
        env_overrides.update({k: v for k, v in args.env_vars})
    agent_model_pairs = args.agent_model_pairs or default_agent_model_pairs

    if args.parallel_dimensions:
        flat_parallel: list[str] = []
        for group in args.parallel_dimensions:
            flat_parallel.extend(group)
    else:
        flat_parallel = list(default_parallel_dimensions)

    run_batch(
        task_ids=args.task_ids,
        tasks_dir=args.tasks_dir,
        output_path=args.output_path,
        exp_settings=exp_settings,
        on_existing=args.on_existing,
        env_overrides=env_overrides,
        agent_model_pairs=agent_model_pairs,
        parallel_dimensions=flat_parallel,
        max_workers=args.max_workers,
        mode=args.mode,
        script_path=args.script_path,
    )


if __name__ == "__main__":
    main()