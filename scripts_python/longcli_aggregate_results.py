#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml

METRIC_KEYS = [
    "agent_duration_time",
    "parser_total_tokens",
    "f2p_is_pass",
    "f2p_step_score",
    "p2p_is_pass",
    "p2p_step_score",
    "all_is_pass",
]

PASS_KEYS = [
    "f2p_is_pass",
    "f2p_step_score",
    "p2p_is_pass",
    "p2p_step_score",
    "all_is_pass",
]

DELTA_BASE_KEYS = [
    "f2p_is_pass",
    "f2p_step_score",
    "p2p_is_pass",
    "p2p_step_score",
    "all_is_pass",
]

DELTA_KEYS = [
    "f2p_is_pass_1to2",
    "f2p_step_score_1to2",
    "p2p_is_pass_1to2",
    "p2p_step_score_1to2",
    "all_is_pass_1to2",
    "f2p_is_pass_2to3",
    "f2p_step_score_2to3",
    "p2p_is_pass_2to3",
    "p2p_step_score_2to3",
    "all_is_pass_2to3",
    "f2p_is_pass_1to3",
    "f2p_step_score_1to3",
    "p2p_is_pass_1to3",
    "p2p_step_score_1to3",
    "all_is_pass_1to3",
]

DEFAULT_INPUT_DIRS = ["runs_long_cli"]
DEFAULT_TASKS_DIR = "tasks_long_cli"
SCORE_BUCKET_LABELS = ["<30%", "30%-60%", "60%-80%", "80-100%", "100%"]
# Example:
# TABLE2_USE_ATTEMPT_LEVEL = True  -> 20 tasks * 3 attempts per task = 60 sub-tasks;
#                                     each attempt is bucketed independently (default).
# TABLE2_USE_ATTEMPT_LEVEL = False -> average 3 attempts per task first, then bucket by 20 tasks.
# If one task has F2P Step Scores 100, 100, 85:
# For True: there are two 100s and one 90.
# For False: there is one value: (100 + 100 + 85) / 3 = 95.
TABLE2_USE_ATTEMPT_LEVEL = True

# === Table generation settings ===
AGENT_DISPLAY_NAMES = {
    "codex": "Codex",
    "claude-code": "Claude Code",
    "openhands": "OpenHands",
}
AGENT_SORT_ORDER = ["codex", "claude-code", "openhands"]
PERCENT_DECIMALS = 3
SCORE_DECIMALS = 3
DURATION_DECIMALS = 3

TABLE1_NAME = "table1_overall.csv"
TABLE2_NAME = "table2_finegrained.csv"
TABLE3_NAME = "table3_selfcorr.csv"
MISSING_REPORT_JSON_NAME = "long_cli_missing_report.json"
MISSING_REPORT_CSV_NAME = "long_cli_missing_report.csv"
# True: leave missing experiment results as missing values.
# False: fill missing results with default zero-score values.
NO_FILL_ZERO_DEFAULT = True

F2P_BUCKET_COLUMNS = [
    ("[0,30)", "<30%"),
    ("[30,60)", "30%-60%"),
    ("[60,80)", "60%-80%"),
    ("[80,100)", "80-100%"),
    ("[100]", "100%"),
]

# False: only match DEFAULT_AGENT_MODEL_PAIRS and DEFAULT_TASK_IDS.
# True: infer from directory names, including pairs/tasks outside DEFAULT_* lists.
DEFAULTS_WHITELIST_DEFAULT = True
# DEFAULTS_WHITELIST_DEFAULT = False

# Use these lists to disambiguate run_dir names when agent/model/task contain underscores.
DEFAULT_AGENT_MODEL_PAIRS = [
    ("<agent_name>", "<model_name>"),
]
# example
# DEFAULT_AGENT_MODEL_PAIRS = [
#     ("codex", "gpt-5.3-codex"),
#     ("codex", "gpt-5.2-codex"),
# ]

DEFAULT_TASK_IDS = [
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
    "ap1400_2_hw26",
    "ap1400_2_hw35",
    "cmu15_445_p0",
    "cmu15_445_p1",
    "cmu15_445_p2",
    "terminal-bench_task",
]

## set ignore agent model pairs
IGNORE_AGENT_MODEL_PAIRS: list[tuple[str, str]] = [
]

## set ignore task ids
IGNORE_TASK_IDS: list[str] = [
]


def _slug(value: str) -> str:
    return (
        value.replace("/", "-")
        .replace("\\", "-")
        .replace(" ", "_")
        .replace(":", "-")
    )


def _normalize_name(value: str) -> str:
    return _slug(value.rsplit("/", 1)[-1] if "/" in value else value)


def _normalize_agent_model_pair(agent: str, model: str) -> tuple[str, str]:
    return _normalize_name(agent), _normalize_name(model)


def _normalize_task_id(task_id: str) -> str:
    return _slug(task_id)


def _build_agent_model_lookup(
    pairs: Iterable[tuple[str, str]],
) -> dict[str, tuple[str, str]]:
    lookup: dict[str, tuple[str, str]] = {}
    for agent, model in pairs:
        key = f"{_normalize_name(agent)}_{_normalize_name(model)}"
        lookup[key] = (agent, model)
    return lookup


def _build_task_lookup(task_ids: Iterable[str]) -> dict[str, str]:
    return {_normalize_task_id(task_id): task_id for task_id in task_ids}


def _parse_run_dir_name(
    run_dir_name: str,
    agent_model_lookup: dict[str, tuple[str, str]],
    task_lookup: dict[str, str],
    task_keys: list[str],
) -> dict[str, Any] | None:
    match = re.search(r"_(\d+)_(\d+)$", run_dir_name)
    if not match:
        return None
    n_attempts = int(match.group(1))
    test_turn = int(match.group(2))
    base = run_dir_name[: match.start()]

    task_id = None
    agent = None
    model = None
    agent_model_part = None

    if task_lookup:
        for key in task_keys:
            if base == key:
                task_id = task_lookup[key]
                agent_model_part = ""
                break
            if base.endswith(f"_{key}"):
                task_id = task_lookup[key]
                agent_model_part = base[: -(len(key) + 1)]
                break

    if agent_model_part:
        pair = agent_model_lookup.get(agent_model_part)
        if pair:
            agent, model = pair

    return {
        "agent": agent,
        "model": model,
        "task_id": task_id,
        "n_attempts": n_attempts,
        "test_turn": test_turn,
    }


def _should_ignore_agent_model(
    agent: str | None, model: str | None, ignore_pairs: set[tuple[str, str]]
) -> bool:
    if not agent or not model:
        return False
    return _normalize_agent_model_pair(agent, model) in ignore_pairs


def _should_ignore_task_id(task_id: str | None, ignore_tasks: set[str]) -> bool:
    if not task_id:
        return False
    return _normalize_task_id(task_id) in ignore_tasks


def _should_allow_agent_model(
    agent: str | None,
    model: str | None,
    whitelist_pairs: set[tuple[str, str]],
    use_whitelist: bool,
) -> bool:
    if not use_whitelist:
        return True
    if not agent or not model:
        return False
    return _normalize_agent_model_pair(agent, model) in whitelist_pairs


def _should_allow_task_id(
    task_id: str | None, whitelist_tasks: set[str], use_whitelist: bool
) -> bool:
    if not use_whitelist:
        return True
    if not task_id:
        return False
    return _normalize_task_id(task_id) in whitelist_tasks


def _empty_metrics(keys: Iterable[str]) -> dict[str, Any]:
    return {k: None for k in keys}


def _coerce_metric(key: str, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    if isinstance(value, bool):
        value = int(value)
    if value in (-1, -1.0):
        return None
    if key.endswith("_is_pass"):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if key == "parser_total_tokens":
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _compute_all_is_pass(f2p_value: Any, p2p_value: Any) -> int | None:
    if f2p_value is None and p2p_value is None:
        return None
    if f2p_value is None:
        return 1 if p2p_value == 1 else 0
    if p2p_value is None:
        return 1 if f2p_value == 1 else 0
    return 1 if f2p_value == 1 and p2p_value == 1 else 0


def _delta_value(value_to: Any, value_from: Any) -> Any:
    if value_to is None or value_from is None:
        return None
    try:
        return round(value_to - value_from, 3)
    except TypeError:
        return None


def _build_turn_deltas(turns: list[dict[str, Any]], expected_turns: int) -> dict[str, Any]:
    if expected_turns < 3:
        return {k: None for k in DELTA_KEYS}
    padded = list(turns[:expected_turns])
    while len(padded) < expected_turns:
        padded.append(_empty_metrics(METRIC_KEYS))

    pairs = {
        "1to2": (0, 1),
        "2to3": (1, 2),
        "1to3": (0, 2),
    }
    out = {k: None for k in DELTA_KEYS}
    for label, (from_idx, to_idx) in pairs.items():
        base_from = padded[from_idx]
        base_to = padded[to_idx]
        for key in DELTA_BASE_KEYS:
            out[f"{key}_{label}"] = _delta_value(base_to.get(key), base_from.get(key))
    return out


def _extract_metrics(raw: dict[str, Any] | None, keys: Iterable[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return _empty_metrics(keys)
    out = {k: _coerce_metric(k, raw.get(k)) for k in keys}
    if "all_is_pass" in out:
        out["all_is_pass"] = _compute_all_is_pass(
            out.get("f2p_is_pass"), out.get("p2p_is_pass")
        )
    return out


def _average_dicts(dicts: list[dict[str, Any]], keys: Iterable[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in keys:
        vals = [d.get(key) for d in dicts if d.get(key) is not None]
        if not vals:
            out[key] = None
            continue
        out[key] = round(sum(vals) / len(vals), 3)
    return out


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] failed to read {path}: {exc}", file=sys.stderr)
        return None


def _load_task_taxonomy(tasks_dir: Path) -> dict[str, dict[str, Any]]:
    if not tasks_dir.exists():
        print(f"[warn] tasks dir not found: {tasks_dir}", file=sys.stderr)
        return {}
    taxonomy: dict[str, dict[str, Any]] = {}
    for child in sorted(tasks_dir.iterdir()):
        if not child.is_dir():
            continue
        task_yaml = child / "task.yaml"
        if not task_yaml.is_file():
            continue
        try:
            data = yaml.safe_load(task_yaml.read_text())
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] failed to read {task_yaml}: {exc}", file=sys.stderr)
            continue
        if not isinstance(data, dict):
            continue
        difficulty = data.get("difficulty")
        category = data.get("category")
        tags = data.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        if not isinstance(tags, list):
            tags = []
        cleaned_tags = [str(tag) for tag in tags if tag is not None]
        taxonomy[child.name] = {
            "difficulty": difficulty,
            "category": category,
            "tags": cleaned_tags,
        }
    return taxonomy


def _task_f2p_step_score(task: dict[str, Any]) -> float | None:
    avg = task.get("3-attempts_avg")
    if isinstance(avg, dict):
        value = avg.get("f2p_step_score")
        if value is not None:
            return value
    turns = task.get("give_test_output")
    if isinstance(turns, list) and turns:
        vals = [row.get("f2p_step_score") for row in turns if row.get("f2p_step_score") is not None]
        if vals:
            return sum(vals) / len(vals)
    return None


def _task_attempt_f2p_scores(task: dict[str, Any]) -> list[float]:
    attempts = task.get("3-attempts")
    if not isinstance(attempts, list):
        return []
    scores: list[float] = []
    for row in attempts:
        if not isinstance(row, dict):
            continue
        value = row.get("f2p_step_score")
        if value is None:
            continue
        scores.append(float(value))
    return scores


def _bucket_f2p_score(value: float) -> str:
    if value < 0.3:
        return "<30%"
    if value < 0.6:
        return "30%-60%"
    if value < 0.8:
        return "60%-80%"
    if value < 1.0:
        return "80-100%"
    return "100%"


def _compute_f2p_score_distribution(
    task_items: list[dict[str, Any]],
) -> dict[str, float]:
    counts = {label: 0 for label in SCORE_BUCKET_LABELS}
    total = 0

    if TABLE2_USE_ATTEMPT_LEVEL:
        for task in task_items:
            for score in _task_attempt_f2p_scores(task):
                bucket = _bucket_f2p_score(score)
                counts[bucket] += 1
                total += 1
    else:
        for task in task_items:
            score = _task_f2p_step_score(task)
            if score is None:
                continue
            bucket = _bucket_f2p_score(score)
            counts[bucket] += 1
            total += 1

    if total == 0:
        return {}
    return {label: round(count / total, 3) for label, count in counts.items()}


def _parse_run_settings(run_id: str) -> tuple[int | None, int | None]:
    match = re.search(r"_(\d+)_(\d+)$", run_id)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _discover_run_dirs(input_dirs: list[str]) -> list[Path]:
    run_dirs: list[Path] = []
    for base in input_dirs:
        base_path = Path(base)
        if not base_path.exists():
            print(f"[warn] input dir not found: {base_path}", file=sys.stderr)
            continue
        for child in base_path.iterdir():
            if child.is_dir() and (child / "results.json").is_file():
                run_dirs.append(child)
    return sorted(run_dirs)


def _init_task_entry() -> dict[str, Any]:
    return {
        "3-attempts": [],
        "3-attempts_avg": {},
        "pass_in_kth": [],
        "pass_at_topk": [],
        "give_test_output": [],
        "give_test_output_delta": {},
    }


def _init_all_results_entry() -> dict[str, Any]:
    return {
        "avg_3-attempts": [],
        "avg_3-attempts_avg": {},
        "avg_pass_in_kth": [],
        "avg_pass_at_topk": [],
        "avg_give_test_output": [],
        "avg_give_test_output_delta": {},
        "f2p_step_score_distribution": {},
    }


def _default_missing_metric_value(key: str, fill_zero: bool) -> Any:
    if not fill_zero:
        return None
    if key == "parser_total_tokens":
        return 0
    if key.endswith("_is_pass"):
        return 0
    if key.endswith("_step_score") or key == "agent_duration_time":
        return 0.0
    return 0


def _default_metrics(keys: Iterable[str], fill_zero: bool) -> dict[str, Any]:
    out = {key: _default_missing_metric_value(key, fill_zero) for key in keys}
    if "all_is_pass" in out:
        out["all_is_pass"] = _compute_all_is_pass(
            out.get("f2p_is_pass"), out.get("p2p_is_pass")
        )
    return out


def _normalize_row_for_fill(
    row: dict[str, Any] | None,
    keys: Iterable[str],
    fill_zero: bool,
) -> dict[str, Any]:
    src = row if isinstance(row, dict) else {}
    key_list = list(keys)
    out: dict[str, Any] = {}
    for key in key_list:
        if key == "all_is_pass":
            continue
        value = _coerce_metric(key, src.get(key))
        if value is None:
            value = _default_missing_metric_value(key, fill_zero)
        out[key] = value
    if "all_is_pass" in key_list:
        out["all_is_pass"] = _compute_all_is_pass(
            out.get("f2p_is_pass"), out.get("p2p_is_pass")
        )
    return out


def _fill_metric_rows(
    rows: list[dict[str, Any]] | Any,
    keys: Iterable[str],
    expected_len: int,
    fill_zero: bool,
) -> list[dict[str, Any]]:
    key_list = list(keys)
    src_rows = rows if isinstance(rows, list) else []
    out = [
        _normalize_row_for_fill(
            row if isinstance(row, dict) else None,
            key_list,
            fill_zero,
        )
        for row in src_rows[:expected_len]
    ]
    while len(out) < expected_len:
        out.append(_default_metrics(key_list, fill_zero))
    return out


def _count_observed_rows(rows: list[dict[str, Any]] | Any, keys: Iterable[str]) -> int:
    if not isinstance(rows, list):
        return 0
    signal_keys = [k for k in keys if k != "all_is_pass"]
    count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if any(row.get(key) is not None for key in signal_keys):
            count += 1
    return count


def _expected_task_ids_for_model(
    tasks: dict[str, Any],
    defaults_whitelist: bool,
    ignore_tasks: set[str],
) -> list[str]:
    if defaults_whitelist:
        return [
            task_id
            for task_id in DEFAULT_TASK_IDS
            if _normalize_task_id(task_id) not in ignore_tasks
        ]
    return sorted(k for k in tasks.keys() if k not in {"all_results", "Taxonomy"})


def _collect_missing_and_fill_tasks(
    summary: dict[str, Any],
    expected_attempts: int,
    expected_turns: int,
    defaults_whitelist: bool,
    ignore_tasks: set[str],
    fill_missing: bool,
    no_fill_zero: bool,
) -> list[dict[str, Any]]:
    fill_zero = not no_fill_zero
    records: list[dict[str, Any]] = []
    for agent, models in summary.items():
        if not isinstance(models, dict):
            continue
        for model, tasks in models.items():
            if not isinstance(tasks, dict):
                continue
            expected_task_ids = _expected_task_ids_for_model(
                tasks, defaults_whitelist, ignore_tasks
            )
            for task_id in expected_task_ids:
                task_data = tasks.get(task_id)
                if not isinstance(task_data, dict):
                    task_data = _init_task_entry()
                    if fill_missing:
                        tasks[task_id] = task_data

                attempts_rows = task_data.get("3-attempts", [])
                turns_rows = task_data.get("give_test_output", [])
                pass_in_kth_rows = task_data.get("pass_in_kth", [])
                pass_at_topk_rows = task_data.get("pass_at_topk", [])

                observed_attempts = _count_observed_rows(attempts_rows, METRIC_KEYS)
                observed_turns = _count_observed_rows(turns_rows, METRIC_KEYS)
                observed_pass_in_kth = _count_observed_rows(pass_in_kth_rows, PASS_KEYS)
                observed_pass_at_topk = _count_observed_rows(pass_at_topk_rows, PASS_KEYS)

                missing_settings: list[str] = []
                if observed_attempts < expected_attempts:
                    missing_settings.append("3_1")
                if observed_turns < expected_turns:
                    missing_settings.append("1_3")
                if observed_pass_in_kth < expected_attempts:
                    missing_settings.append("pass_in_kth")
                if observed_pass_at_topk < expected_attempts:
                    missing_settings.append("pass_at_topk")

                if missing_settings:
                    records.append(
                        {
                            "agent": agent,
                            "model": model,
                            "task_id": task_id,
                            "missing_settings": ",".join(missing_settings),
                            "observed_3_1_rows": observed_attempts,
                            "expected_3_1_rows": expected_attempts,
                            "observed_1_3_rows": observed_turns,
                            "expected_1_3_rows": expected_turns,
                            "observed_pass_in_kth_rows": observed_pass_in_kth,
                            "expected_pass_in_kth_rows": expected_attempts,
                            "observed_pass_at_topk_rows": observed_pass_at_topk,
                            "expected_pass_at_topk_rows": expected_attempts,
                        }
                    )

                if not fill_missing:
                    continue

                task_data["3-attempts"] = _fill_metric_rows(
                    attempts_rows, METRIC_KEYS, expected_attempts, fill_zero
                )
                task_data["3-attempts_avg"] = _average_dicts(
                    task_data["3-attempts"], METRIC_KEYS
                )
                task_data["pass_in_kth"] = _fill_metric_rows(
                    pass_in_kth_rows, PASS_KEYS, expected_attempts, fill_zero
                )
                task_data["pass_at_topk"] = _fill_metric_rows(
                    pass_at_topk_rows, PASS_KEYS, expected_attempts, fill_zero
                )
                task_data["give_test_output"] = _fill_metric_rows(
                    turns_rows, METRIC_KEYS, expected_turns, fill_zero
                )
                task_data["give_test_output_delta"] = _build_turn_deltas(
                    task_data["give_test_output"], expected_turns
                )
                tasks[task_id] = task_data
    return records


def _build_attempt_list(
    attempts: list[list[dict[str, Any]]], expected_attempts: int
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for attempt in attempts[:expected_attempts]:
        first_turn = attempt[0] if attempt else None
        out.append(_extract_metrics(first_turn, METRIC_KEYS))
    while len(out) < expected_attempts:
        out.append(_empty_metrics(METRIC_KEYS))
    return out


def _build_turn_list(
    attempts: list[list[dict[str, Any]]], expected_turns: int
) -> list[dict[str, Any]]:
    turns = attempts[0] if attempts else []
    out = [_extract_metrics(turn, METRIC_KEYS) for turn in turns[:expected_turns]]
    while len(out) < expected_turns:
        out.append(_empty_metrics(METRIC_KEYS))
    return out


def _build_pass_list(
    lna_task: dict[str, Any] | None,
    key: str,
    expected_attempts: int,
) -> list[dict[str, Any]]:
    rows = []
    if isinstance(lna_task, dict):
        rows = lna_task.get(key, []) or []
    if not rows:
        return []
    out: list[dict[str, Any]] = []
    for row in rows[:expected_attempts]:
        first_turn = row[0] if row else None
        out.append(_extract_metrics(first_turn, PASS_KEYS))
    while len(out) < expected_attempts:
        out.append(_empty_metrics(PASS_KEYS))
    return out


def _load_long_cli_n_attempts(results: dict[str, Any]) -> dict[str, Any]:
    lna = results.get("long_cli_n_attempts")
    if isinstance(lna, dict):
        return lna
    compact = results.get("long_cli_n_attempts_compact")
    if isinstance(compact, dict):
        return compact
    if isinstance(compact, str):
        try:
            parsed = json.loads(compact)
            if isinstance(parsed, dict):
                return parsed
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _merge_task_data(
    task_data: dict[str, Any],
    attempts: list[list[dict[str, Any]]],
    lna: dict[str, Any],
    task_id: str,
    n_attempts: int,
    test_turn: int,
    expected_attempts: int,
    expected_turns: int,
) -> None:
    if n_attempts == 3 and test_turn == 1:
        task_data["3-attempts"] = _build_attempt_list(attempts, expected_attempts)
        task_data["3-attempts_avg"] = _average_dicts(
            task_data["3-attempts"], METRIC_KEYS
        )
        lna_task = lna.get(task_id, {}) if isinstance(lna, dict) else {}
        task_data["pass_in_kth"] = _build_pass_list(
            lna_task, "pass_in_kth", expected_attempts
        )
        task_data["pass_at_topk"] = _build_pass_list(
            lna_task, "pass_at_topk", expected_attempts
        )
        return
    if n_attempts == 1 and test_turn == 3:
        task_data["give_test_output"] = _build_turn_list(attempts, expected_turns)
        task_data["give_test_output_delta"] = _build_turn_deltas(
            task_data["give_test_output"], expected_turns
        )
        return
    print(
        f"[warn] skipping unsupported setting n_attempts={n_attempts}, test_turn={test_turn}",
        file=sys.stderr,
    )


def build_summary(
    input_dirs: list[str],
    expected_attempts: int,
    expected_turns: int,
    defaults_whitelist: bool = DEFAULTS_WHITELIST_DEFAULT,
    tasks_dir: str | None = DEFAULT_TASKS_DIR,
    fill_missing: bool = True,
    missing_records_out: list[dict[str, Any]] | None = None,
    no_fill_zero: bool = NO_FILL_ZERO_DEFAULT,
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    taxonomy_map = (
        _load_task_taxonomy(Path(tasks_dir)) if tasks_dir else {}
    )

    known_pairs = DEFAULT_AGENT_MODEL_PAIRS + IGNORE_AGENT_MODEL_PAIRS
    known_tasks = DEFAULT_TASK_IDS + IGNORE_TASK_IDS
    agent_model_lookup = _build_agent_model_lookup(known_pairs)
    task_lookup = _build_task_lookup(known_tasks)
    task_keys = sorted(task_lookup, key=len, reverse=True)

    whitelist_pairs = {
        _normalize_agent_model_pair(agent, model)
        for agent, model in DEFAULT_AGENT_MODEL_PAIRS
    }
    whitelist_tasks = {_normalize_task_id(task_id) for task_id in DEFAULT_TASK_IDS}

    ignore_pairs = {
        _normalize_agent_model_pair(agent, model)
        for agent, model in IGNORE_AGENT_MODEL_PAIRS
    }
    ignore_tasks = {_normalize_task_id(task_id) for task_id in IGNORE_TASK_IDS}

    for run_dir in _discover_run_dirs(input_dirs):
        parsed = _parse_run_dir_name(
            run_dir.name, agent_model_lookup, task_lookup, task_keys
        )
        if parsed:
            if not _should_allow_task_id(
                parsed.get("task_id"), whitelist_tasks, defaults_whitelist
            ):
                print(
                    f"[info] skipping non-whitelist task run: {run_dir}",
                    file=sys.stdout,
                )
                continue
            if not _should_allow_agent_model(
                parsed.get("agent"), parsed.get("model"), whitelist_pairs, defaults_whitelist
            ):
                print(
                    f"[info] skipping non-whitelist agent/model run: {run_dir}",
                    file=sys.stdout,
                )
                continue
            if _should_ignore_task_id(parsed.get("task_id"), ignore_tasks):
                print(f"[info] skipping ignored task run: {run_dir}", file=sys.stdout)
                continue
            if _should_ignore_agent_model(
                parsed.get("agent"), parsed.get("model"), ignore_pairs
            ):
                print(
                    f"[info] skipping ignored agent/model run: {run_dir}",
                    file=sys.stdout,
                )
                continue

        results = _load_json(run_dir / "results.json")
        metadata = _load_json(run_dir / "run_metadata.json")
        if not isinstance(results, dict) or not results:
            continue
        metadata = metadata if isinstance(metadata, dict) else {}

        agent = metadata.get("agent_name") or (parsed.get("agent") if parsed else None) or "unknown"
        model = metadata.get("model_name") or (parsed.get("model") if parsed else None) or "unknown"
        run_id = metadata.get("run_id") or run_dir.name

        n_attempts, test_turn = _parse_run_settings(run_id)
        if n_attempts is None or test_turn is None:
            if parsed and parsed.get("n_attempts") is not None:
                n_attempts = parsed["n_attempts"]
                test_turn = parsed["test_turn"]
            else:
                n_attempts, test_turn = _parse_run_settings(run_dir.name)
        if n_attempts is None or test_turn is None:
            print(f"[warn] unable to parse run_id: {run_id}", file=sys.stderr)
            continue

        print(
            f"[info] parsed run_id: {run_id} (n_attempts={n_attempts}, test_turn={test_turn})",
            file=sys.stdout,
        )

        if not _should_allow_agent_model(agent, model, whitelist_pairs, defaults_whitelist):
            print(
                f"[info] skipping non-whitelist agent/model run: {run_dir}",
                file=sys.stdout,
            )
            continue

        if _should_ignore_agent_model(agent, model, ignore_pairs):
            print(
                f"[info] skipping ignored agent/model run: {run_dir}",
                file=sys.stdout,
            )
            continue

        lcar = results.get("long_cli_all_results") or {}
        if not isinstance(lcar, dict) or not lcar:
            continue
        lna = _load_long_cli_n_attempts(results)

        filtered_items: list[tuple[str, list[list[dict[str, Any]]]]] = []
        for task_id, attempts in lcar.items():
            if not _should_allow_task_id(task_id, whitelist_tasks, defaults_whitelist):
                continue
            if _should_ignore_task_id(task_id, ignore_tasks):
                continue
            if not isinstance(attempts, list):
                continue
            filtered_items.append((task_id, attempts))

        if not filtered_items:
            continue

        agent_data = summary.setdefault(agent, {})
        model_data = agent_data.setdefault(model, {})
        for task_id, attempts in filtered_items:
            task_data = model_data.setdefault(task_id, _init_task_entry())
            _merge_task_data(
                task_data,
                attempts,
                lna,
                task_id,
                n_attempts,
                test_turn,
                expected_attempts,
                expected_turns,
            )

    missing_records = _collect_missing_and_fill_tasks(
        summary,
        expected_attempts,
        expected_turns,
        defaults_whitelist,
        ignore_tasks,
        fill_missing,
        no_fill_zero,
    )
    if missing_records_out is not None:
        missing_records_out.extend(missing_records)

    for agent, models in summary.items():
        for model, tasks in models.items():
            task_items = [v for k, v in tasks.items() if k not in {"all_results", "Taxonomy"}]
            tasks["all_results"] = _compute_all_results(
                task_items, expected_attempts, expected_turns
            )
            tasks["Taxonomy"] = _compute_taxonomy_results(
                tasks, taxonomy_map, expected_attempts, expected_turns
            )
    return summary


def _compute_all_results(
    task_items: list[dict[str, Any]], expected_attempts: int, expected_turns: int
) -> dict[str, Any]:
    all_results = _init_all_results_entry()

    def build_avg_list(field: str, keys: list[str], length: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        any_data = False
        for idx in range(length):
            dicts = []
            for item in task_items:
                arr = item.get(field, [])
                if isinstance(arr, list) and len(arr) > idx:
                    dicts.append(arr[idx])
            if dicts:
                any_data = True
                rows.append(_average_dicts(dicts, keys))
            else:
                rows.append(_empty_metrics(keys))
        return rows if any_data else []

    all_results["avg_3-attempts"] = build_avg_list(
        "3-attempts", METRIC_KEYS, expected_attempts
    )
    all_results["avg_give_test_output"] = build_avg_list(
        "give_test_output", METRIC_KEYS, expected_turns
    )
    all_results["avg_pass_in_kth"] = build_avg_list(
        "pass_in_kth", PASS_KEYS, expected_attempts
    )
    all_results["avg_pass_at_topk"] = build_avg_list(
        "pass_at_topk", PASS_KEYS, expected_attempts
    )
    delta_candidates = [
        t.get("give_test_output_delta")
        for t in task_items
        if isinstance(t.get("give_test_output_delta"), dict) and t.get("give_test_output_delta")
    ]
    all_results["avg_give_test_output_delta"] = (
        _average_dicts(delta_candidates, DELTA_KEYS) if delta_candidates else {}
    )

    avg_candidates = [t.get("3-attempts_avg") for t in task_items if t.get("3-attempts_avg")]
    all_results["avg_3-attempts_avg"] = (
        _average_dicts(avg_candidates, METRIC_KEYS) if avg_candidates else {}
    )
    all_results["f2p_step_score_distribution"] = _compute_f2p_score_distribution(task_items)

    return all_results


def _compute_taxonomy_results(
    tasks: dict[str, Any],
    taxonomy_map: dict[str, dict[str, Any]],
    expected_attempts: int,
    expected_turns: int,
) -> dict[str, Any]:
    grouped: dict[str, dict[str, list[tuple[str, dict[str, Any]]]]] = {
        "difficulty": {},
        "category": {},
        "domain": {},
    }

    def add_group(group_type: str, key: str, task_id: str, task_data: dict[str, Any]) -> None:
        grouped[group_type].setdefault(key, []).append((task_id, task_data))

    for task_id, task_data in tasks.items():
        if task_id in {"all_results", "Taxonomy"}:
            continue
        meta = taxonomy_map.get(task_id)
        if not isinstance(meta, dict):
            continue
        difficulty = meta.get("difficulty")
        if difficulty:
            add_group("difficulty", str(difficulty), task_id, task_data)
        category = meta.get("category")
        if category:
            add_group("category", str(category), task_id, task_data)
        tags = meta.get("tags") or []
        if isinstance(tags, list):
            for tag in dict.fromkeys(tags):
                if tag:
                    add_group("domain", str(tag), task_id, task_data)

    taxonomy_results: dict[str, Any] = {"difficulty": {}, "category": {}, "domain": {}}
    for group_type, groups in grouped.items():
        for key, items in groups.items():
            task_items = [item for _, item in items]
            result = _compute_all_results(task_items, expected_attempts, expected_turns)
            result["task_ids"] = sorted({task_id for task_id, _ in items})
            taxonomy_results[group_type][key] = result
    return taxonomy_results


# === Table helpers ===
def _display_agent(agent: str) -> str:
    return AGENT_DISPLAY_NAMES.get(agent, agent)


def _sort_agents(agents: Iterable[str]) -> list[str]:
    order_map = {name: idx for idx, name in enumerate(AGENT_SORT_ORDER)}
    return sorted(agents, key=lambda name: (order_map.get(name, 999), name))


def _iter_agent_models(summary: dict[str, Any]) -> Iterable[tuple[str, str, dict[str, Any]]]:
    for agent in _sort_agents(summary.keys()):
        models = summary.get(agent)
        if not isinstance(models, dict):
            continue
        for model in sorted(models.keys()):
            model_data = models.get(model)
            if isinstance(model_data, dict):
                yield agent, model, model_data


def _round_value(value: Any, decimals: int) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return None


def _to_percent(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), PERCENT_DECIMALS)
    except (TypeError, ValueError):
        return None


def _seconds_to_minutes(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value) / 60.0, DURATION_DECIMALS)
    except (TypeError, ValueError):
        return None


def _avg(values: Iterable[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _delta_value(value_to: Any, value_from: Any) -> float | None:
    if value_to is None or value_from is None:
        return None
    try:
        return round(float(value_to) - float(value_from), 3)
    except (TypeError, ValueError):
        return None


def _get_all_results(model_data: dict[str, Any]) -> dict[str, Any]:
    all_results = model_data.get("all_results")
    return all_results if isinstance(all_results, dict) else {}


def _get_avg_attempts_avg(all_results: dict[str, Any]) -> dict[str, Any]:
    avg = all_results.get("avg_3-attempts_avg")
    return avg if isinstance(avg, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _get_turn_metric(all_results: dict[str, Any], index: int, key: str) -> Any:
    turns = _safe_list(all_results.get("avg_give_test_output"))
    if index < len(turns) and isinstance(turns[index], dict):
        return turns[index].get(key)
    return None


def _get_delta_metric(all_results: dict[str, Any], key: str) -> Any:
    delta = all_results.get("avg_give_test_output_delta")
    if isinstance(delta, dict):
        return delta.get(key)
    return None


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


# === Table 1: Overall summary ===
def _build_table1(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for agent, model, model_data in _iter_agent_models(summary):
        all_results = _get_all_results(model_data)
        avg = _get_avg_attempts_avg(all_results)
        pass_at_topk = _safe_list(all_results.get("avg_pass_at_topk"))
        pass_at_3 = None
        if len(pass_at_topk) > 2 and isinstance(pass_at_topk[2], dict):
            pass_at_3 = pass_at_topk[2].get("all_is_pass")
        row = {
            "Agent": _display_agent(agent),
            "Backend": model,
            "Avg Pass Rate (%)": _to_percent(avg.get("all_is_pass")),
            "Pass@3 (%)": _to_percent(pass_at_3),
            "F2P Pass Rate (%)": _to_percent(avg.get("f2p_is_pass")),
            "P2P Pass Rate (%)": _to_percent(avg.get("p2p_is_pass")),
            "Avg F2P Step Score": _to_percent(avg.get("f2p_step_score")),
            "Avg P2P Step Score": _to_percent(avg.get("p2p_step_score")),
            "Avg Duration (min)": _seconds_to_minutes(avg.get("agent_duration_time")),
        }
        rows.append(row)
    return rows


def _write_table1(summary: dict[str, Any], output_dir: Path) -> None:
    rows = _build_table1(summary)
    columns = [
        "Agent",
        "Backend",
        "Avg Pass Rate (%)",
        "Pass@3 (%)",
        "F2P Pass Rate (%)",
        "P2P Pass Rate (%)",
        "Avg F2P Step Score",
        "Avg P2P Step Score",
        "Avg Duration (min)",
    ]
    _write_csv(output_dir / TABLE1_NAME, columns, rows)


# === Table 2: Fine-grained F2P distribution ===
def _build_table2(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for agent, model, model_data in _iter_agent_models(summary):
        all_results = _get_all_results(model_data)
        distribution = all_results.get("f2p_step_score_distribution")
        distribution = distribution if isinstance(distribution, dict) else {}
        row = {
            "Agent": _display_agent(agent),
            "Model": model,
        }
        for column, key in F2P_BUCKET_COLUMNS:
            row[column] = _to_percent(distribution.get(key))
        rows.append(row)
    return rows


def _write_table2(summary: dict[str, Any], output_dir: Path) -> None:
    rows = _build_table2(summary)
    columns = ["Agent", "Model"] + [col for col, _ in F2P_BUCKET_COLUMNS]
    _write_csv(output_dir / TABLE2_NAME, columns, rows)


# === Table 3: Self-correction across turns ===
def _build_table3(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for agent, model, model_data in _iter_agent_models(summary):
        all_results = _get_all_results(model_data)
        t1_pass = _get_turn_metric(all_results, 0, "all_is_pass")
        t2_pass = _get_turn_metric(all_results, 1, "all_is_pass")
        t3_pass = _get_turn_metric(all_results, 2, "all_is_pass")
        t1_duration = _get_turn_metric(all_results, 0, "agent_duration_time")
        t2_duration = _get_turn_metric(all_results, 1, "agent_duration_time")
        t3_duration = _get_turn_metric(all_results, 2, "agent_duration_time")
        t1_f2p_pass = _get_turn_metric(all_results, 0, "f2p_is_pass")
        t2_f2p_pass = _get_turn_metric(all_results, 1, "f2p_is_pass")
        t3_f2p_pass = _get_turn_metric(all_results, 2, "f2p_is_pass")
        t1_p2p_pass = _get_turn_metric(all_results, 0, "p2p_is_pass")
        t2_p2p_pass = _get_turn_metric(all_results, 1, "p2p_is_pass")
        t3_p2p_pass = _get_turn_metric(all_results, 2, "p2p_is_pass")
        t1_f2p_score = _get_turn_metric(all_results, 0, "f2p_step_score")
        t2_f2p_score = _get_turn_metric(all_results, 1, "f2p_step_score")
        t3_f2p_score = _get_turn_metric(all_results, 2, "f2p_step_score")
        t1_p2p_score = _get_turn_metric(all_results, 0, "p2p_step_score")
        t2_p2p_score = _get_turn_metric(all_results, 1, "p2p_step_score")
        t3_p2p_score = _get_turn_metric(all_results, 2, "p2p_step_score")

        combined_t1 = _avg([t1_f2p_score, t1_p2p_score])
        combined_t2 = _avg([t2_f2p_score, t2_p2p_score])
        combined_t3 = _avg([t3_f2p_score, t3_p2p_score])

        row = {
            "Agent": _display_agent(agent),
            "Model": model,
            "T1 Pass Rate (%)": _to_percent(t1_pass),
            "T2 Pass Rate (%)": _to_percent(t2_pass),
            "T3 Pass Rate (%)": _to_percent(t3_pass),
            "T1 Duration (min)": _seconds_to_minutes(t1_duration),
            "T2 Duration (min)": _seconds_to_minutes(t2_duration),
            "T3 Duration (min)": _seconds_to_minutes(t3_duration),
            "T1 F2P Pass Rate (%)": _to_percent(t1_f2p_pass),
            "T2 F2P Pass Rate (%)": _to_percent(t2_f2p_pass),
            "T3 F2P Pass Rate (%)": _to_percent(t3_f2p_pass),
            "T1 P2P Pass Rate (%)": _to_percent(t1_p2p_pass),
            "T2 P2P Pass Rate (%)": _to_percent(t2_p2p_pass),
            "T3 P2P Pass Rate (%)": _to_percent(t3_p2p_pass),
            "T1 F2P Step Score": _to_percent(t1_f2p_score),
            "T2 F2P Step Score": _to_percent(t2_f2p_score),
            "T3 F2P Step Score": _to_percent(t3_f2p_score),
            "T1 P2P Step Score": _to_percent(t1_p2p_score),
            "T2 P2P Step Score": _to_percent(t2_p2p_score),
            "T3 P2P Step Score": _to_percent(t3_p2p_score),
            "Δ Pass (T1->T2)": _to_percent(_get_delta_metric(all_results, "all_is_pass_1to2")),
            "Δ Pass (T2->T3)": _to_percent(_get_delta_metric(all_results, "all_is_pass_2to3")),
            "Δ Pass (T1->T3)": _to_percent(_get_delta_metric(all_results, "all_is_pass_1to3")),
            "Δ F2P Pass (T1->T2)": _to_percent(_get_delta_metric(all_results, "f2p_is_pass_1to2")),
            "Δ F2P Pass (T2->T3)": _to_percent(_get_delta_metric(all_results, "f2p_is_pass_2to3")),
            "Δ F2P Pass (T1->T3)": _to_percent(_get_delta_metric(all_results, "f2p_is_pass_1to3")),
            "Δ P2P Pass (T1->T2)": _to_percent(_get_delta_metric(all_results, "p2p_is_pass_1to2")),
            "Δ P2P Pass (T2->T3)": _to_percent(_get_delta_metric(all_results, "p2p_is_pass_2to3")),
            "Δ P2P Pass (T1->T3)": _to_percent(_get_delta_metric(all_results, "p2p_is_pass_1to3")),
            "Δ Step Score (T1->T2)": _to_percent(_delta_value(combined_t2, combined_t1)),
            "Δ Step Score (T2->T3)": _to_percent(_delta_value(combined_t3, combined_t2)),
            "Δ Step Score (T1->T3)": _to_percent(_delta_value(combined_t3, combined_t1)),
            "Δ F2P Step Score (T1->T2)": _to_percent(
                _get_delta_metric(all_results, "f2p_step_score_1to2")
            ),
            "Δ F2P Step Score (T2->T3)": _to_percent(
                _get_delta_metric(all_results, "f2p_step_score_2to3")
            ),
            "Δ F2P Step Score (T1->T3)": _to_percent(
                _get_delta_metric(all_results, "f2p_step_score_1to3")
            ),
            "Δ P2P Step Score (T1->T2)": _to_percent(
                _get_delta_metric(all_results, "p2p_step_score_1to2")
            ),
            "Δ P2P Step Score (T2->T3)": _to_percent(
                _get_delta_metric(all_results, "p2p_step_score_2to3")
            ),
            "Δ P2P Step Score (T1->T3)": _to_percent(
                _get_delta_metric(all_results, "p2p_step_score_1to3")
            ),
        }
        rows.append(row)
    return rows


def _write_table3(summary: dict[str, Any], output_dir: Path) -> None:
    rows = _build_table3(summary)
    columns = [
        "Agent",
        "Model",
        "T1 Pass Rate (%)",
        "T2 Pass Rate (%)",
        "T3 Pass Rate (%)",
        "T1 Duration (min)",
        "T2 Duration (min)",
        "T3 Duration (min)",
        "T1 F2P Pass Rate (%)",
        "T2 F2P Pass Rate (%)",
        "T3 F2P Pass Rate (%)",
        "T1 P2P Pass Rate (%)",
        "T2 P2P Pass Rate (%)",
        "T3 P2P Pass Rate (%)",
        "T1 F2P Step Score",
        "T2 F2P Step Score",
        "T3 F2P Step Score",
        "T1 P2P Step Score",
        "T2 P2P Step Score",
        "T3 P2P Step Score",
        "Δ Pass (T1->T2)",
        "Δ Pass (T2->T3)",
        "Δ Pass (T1->T3)",
        "Δ F2P Pass (T1->T2)",
        "Δ F2P Pass (T2->T3)",
        "Δ F2P Pass (T1->T3)",
        "Δ P2P Pass (T1->T2)",
        "Δ P2P Pass (T2->T3)",
        "Δ P2P Pass (T1->T3)",
        "Δ Step Score (T1->T2)",
        "Δ Step Score (T2->T3)",
        "Δ Step Score (T1->T3)",
        "Δ F2P Step Score (T1->T2)",
        "Δ F2P Step Score (T2->T3)",
        "Δ F2P Step Score (T1->T3)",
        "Δ P2P Step Score (T1->T2)",
        "Δ P2P Step Score (T2->T3)",
        "Δ P2P Step Score (T1->T3)",
    ]
    _write_csv(output_dir / TABLE3_NAME, columns, rows)


def write_tables(summary: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_table1(summary, output_dir)
    _write_table2(summary, output_dir)
    _write_table3(summary, output_dir)


def write_json(summary: dict[str, Any], output_path: Path) -> None:
    output_path.write_text(json.dumps(summary, indent=4, ensure_ascii=True))


def write_csv(summary: dict[str, Any], output_path: Path) -> None:
    columns = [
        "agent",
        "model",
        "task_id",
        "section",
        "attempt_index",
        "turn_index",
        "k_index",
        "taxonomy_type",
        "taxonomy_value",
        "score_bucket",
        "score_ratio",
        "agent_duration_time",
        "parser_total_tokens",
        "f2p_is_pass",
        "f2p_step_score",
        "p2p_is_pass",
        "p2p_step_score",
        "all_is_pass",
    ] + DELTA_KEYS
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for agent, models in summary.items():
            for model, tasks in models.items():
                for task_id, task_data in tasks.items():
                    if task_id in {"all_results", "Taxonomy"}:
                        continue
                    _write_task_rows(writer, agent, model, task_id, task_data)
                all_results = tasks.get("all_results", {})
                _write_all_results_rows(writer, agent, model, all_results)
                taxonomy = tasks.get("Taxonomy", {})
                _write_taxonomy_rows(writer, agent, model, taxonomy)


def write_missing_reports(
    missing_records: list[dict[str, Any]],
    output_json_path: Path,
    output_csv_path: Path,
) -> None:
    output_json_path.write_text(
        json.dumps(missing_records, indent=4, ensure_ascii=True)
    )
    columns = [
        "agent",
        "model",
        "task_id",
        "missing_settings",
        "observed_3_1_rows",
        "expected_3_1_rows",
        "observed_1_3_rows",
        "expected_1_3_rows",
        "observed_pass_in_kth_rows",
        "expected_pass_in_kth_rows",
        "observed_pass_at_topk_rows",
        "expected_pass_at_topk_rows",
    ]
    with output_csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in missing_records:
            writer.writerow(row)


def _write_task_rows(
    writer: csv.DictWriter,
    agent: str,
    model: str,
    task_id: str,
    task_data: dict[str, Any],
) -> None:
    for idx, row in enumerate(task_data.get("3-attempts", []), start=1):
        writer.writerow(
            _base_row(agent, model, task_id, "3-attempts", attempt_index=idx) | row
        )
    if task_data.get("3-attempts_avg"):
        writer.writerow(
            _base_row(agent, model, task_id, "3-attempts_avg")
            | task_data["3-attempts_avg"]
        )
    for idx, row in enumerate(task_data.get("pass_in_kth", []), start=1):
        writer.writerow(_base_row(agent, model, task_id, "pass_in_kth", k_index=idx) | row)
    for idx, row in enumerate(task_data.get("pass_at_topk", []), start=1):
        writer.writerow(_base_row(agent, model, task_id, "pass_at_topk", k_index=idx) | row)
    for idx, row in enumerate(task_data.get("give_test_output", []), start=1):
        writer.writerow(
            _base_row(agent, model, task_id, "give_test_output", turn_index=idx) | row
        )
    if task_data.get("give_test_output_delta"):
        writer.writerow(
            _base_row(agent, model, task_id, "give_test_output_delta")
            | task_data["give_test_output_delta"]
        )


def _write_all_results_rows(
    writer: csv.DictWriter,
    agent: str,
    model: str,
    all_results: dict[str, Any],
    taxonomy_type: str | None = None,
    taxonomy_value: str | None = None,
) -> None:
    for idx, row in enumerate(all_results.get("avg_3-attempts", []), start=1):
        writer.writerow(
            _base_row(
                agent,
                model,
                "",
                "avg_3-attempts",
                attempt_index=idx,
                taxonomy_type=taxonomy_type,
                taxonomy_value=taxonomy_value,
            )
            | row
        )
    if all_results.get("avg_3-attempts_avg"):
        writer.writerow(
            _base_row(
                agent,
                model,
                "",
                "avg_3-attempts_avg",
                taxonomy_type=taxonomy_type,
                taxonomy_value=taxonomy_value,
            )
            | all_results["avg_3-attempts_avg"]
        )
    for idx, row in enumerate(all_results.get("avg_pass_in_kth", []), start=1):
        writer.writerow(
            _base_row(
                agent,
                model,
                "",
                "avg_pass_in_kth",
                k_index=idx,
                taxonomy_type=taxonomy_type,
                taxonomy_value=taxonomy_value,
            )
            | row
        )
    for idx, row in enumerate(all_results.get("avg_pass_at_topk", []), start=1):
        writer.writerow(
            _base_row(
                agent,
                model,
                "",
                "avg_pass_at_topk",
                k_index=idx,
                taxonomy_type=taxonomy_type,
                taxonomy_value=taxonomy_value,
            )
            | row
        )
    for idx, row in enumerate(all_results.get("avg_give_test_output", []), start=1):
        writer.writerow(
            _base_row(
                agent,
                model,
                "",
                "avg_give_test_output",
                turn_index=idx,
                taxonomy_type=taxonomy_type,
                taxonomy_value=taxonomy_value,
            )
            | row
        )
    if all_results.get("avg_give_test_output_delta"):
        writer.writerow(
            _base_row(
                agent,
                model,
                "",
                "avg_give_test_output_delta",
                taxonomy_type=taxonomy_type,
                taxonomy_value=taxonomy_value,
            )
            | all_results["avg_give_test_output_delta"]
        )
    _write_distribution_rows(
        writer,
        agent,
        model,
        all_results.get("f2p_step_score_distribution", {}),
        taxonomy_type=taxonomy_type,
        taxonomy_value=taxonomy_value,
    )


def _write_taxonomy_rows(
    writer: csv.DictWriter,
    agent: str,
    model: str,
    taxonomy: dict[str, Any],
) -> None:
    if not isinstance(taxonomy, dict):
        return
    for taxonomy_type, groups in taxonomy.items():
        if not isinstance(groups, dict):
            continue
        for taxonomy_value, results in groups.items():
            if not isinstance(results, dict):
                continue
            _write_all_results_rows(
                writer,
                agent,
                model,
                results,
                taxonomy_type=str(taxonomy_type),
                taxonomy_value=str(taxonomy_value),
            )


def _write_distribution_rows(
    writer: csv.DictWriter,
    agent: str,
    model: str,
    distribution: dict[str, Any],
    taxonomy_type: str | None = None,
    taxonomy_value: str | None = None,
) -> None:
    if not isinstance(distribution, dict) or not distribution:
        return
    for bucket, ratio in distribution.items():
        row = _base_row(
            agent,
            model,
            "",
            "f2p_step_score_distribution",
            taxonomy_type=taxonomy_type,
            taxonomy_value=taxonomy_value,
            score_bucket=bucket,
            score_ratio=ratio,
        )
        writer.writerow(row)


def _base_row(
    agent: str,
    model: str,
    task_id: str,
    section: str,
    attempt_index: int | None = None,
    turn_index: int | None = None,
    k_index: int | None = None,
    taxonomy_type: str | None = None,
    taxonomy_value: str | None = None,
    score_bucket: str | None = None,
    score_ratio: float | None = None,
) -> dict[str, Any]:
    return {
        "agent": agent,
        "model": model,
        "task_id": task_id,
        "section": section,
        "attempt_index": attempt_index,
        "turn_index": turn_index,
        "k_index": k_index,
        "taxonomy_type": taxonomy_type,
        "taxonomy_value": taxonomy_value,
        "score_bucket": score_bucket,
        "score_ratio": score_ratio,
        "agent_duration_time": None,
        "parser_total_tokens": None,
        "f2p_is_pass": None,
        "f2p_step_score": None,
        "p2p_is_pass": None,
        "p2p_step_score": None,
        "all_is_pass": None,
        **{key: None for key in DELTA_KEYS},
    }


def _parse_bool(raw: str) -> bool:
    value = raw.strip().lower()
    if value in {"true", "1", "yes", "y"}:
        return True
    if value in {"false", "0", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError("Use True or False.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate long_cli results into JSON and CSV summaries."
    )
    parser.add_argument(
        "--input-dirs",
        nargs="+",
        default=DEFAULT_INPUT_DIRS,
        help="Parent directories containing run outputs.",
    )
    parser.add_argument(
        "--output-json",
        default="long_cli_summary.json",
        help="Output JSON path.",
    )
    parser.add_argument(
        "--output-csv",
        default="long_cli_summary.csv",
        help="Output CSV path.",
    )
    parser.add_argument(
        "--expected-attempts",
        type=int,
        default=3,
        help="Expected attempts for 3_1 runs.",
    )
    parser.add_argument(
        "--expected-turns",
        type=int,
        default=3,
        help="Expected turns for 1_3 runs.",
    )
    parser.add_argument(
        "--defaults-whitelist",
        type=_parse_bool,
        default=DEFAULTS_WHITELIST_DEFAULT,
        help="Use DEFAULT_* lists as whitelist filters (True/False).",
    )
    parser.add_argument(
        "--tasks-dir",
        default=DEFAULT_TASKS_DIR,
        help="Directory containing task.yaml metadata for taxonomy stats.",
    )
    parser.add_argument(
        "--write-tables",
        type=_parse_bool,
        default=True,
        help="Write summary tables (True/False).",
    )
    parser.add_argument(
        "--tables-dir",
        default=".",
        help="Directory to write table CSV files.",
    )
    parser.add_argument(
        "--fill-missing",
        type=_parse_bool,
        default=True,
        help="Fill missing model-task settings with default failure rows (True/False).",
    )
    parser.add_argument(
        "--no-fill-zero",
        type=_parse_bool,
        default=NO_FILL_ZERO_DEFAULT,
        help="Do not fill missing metric values with zero (True/False).",
    )
    parser.add_argument(
        "--output-missing-json",
        default=MISSING_REPORT_JSON_NAME,
        help="Output JSON path for missing model-task coverage report.",
    )
    parser.add_argument(
        "--output-missing-csv",
        default=MISSING_REPORT_CSV_NAME,
        help="Output CSV path for missing model-task coverage report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    missing_records: list[dict[str, Any]] = []
    summary = build_summary(
        input_dirs=args.input_dirs,
        expected_attempts=args.expected_attempts,
        expected_turns=args.expected_turns,
        defaults_whitelist=args.defaults_whitelist,
        tasks_dir=args.tasks_dir,
        fill_missing=args.fill_missing,
        missing_records_out=missing_records,
        no_fill_zero=args.no_fill_zero,
    )
    json_path = Path(args.output_json).resolve()
    csv_path = Path(args.output_csv).resolve()
    missing_json_path = Path(args.output_missing_json).resolve()
    missing_csv_path = Path(args.output_missing_csv).resolve()
    write_json(summary, json_path)
    write_csv(summary, csv_path)
    write_missing_reports(missing_records, missing_json_path, missing_csv_path)
    if args.write_tables:
        tables_dir = Path(args.tables_dir).resolve()
        write_tables(summary, tables_dir)
        print(f"Table1 saved to: {tables_dir / TABLE1_NAME}")
        print(f"Table2 saved to: {tables_dir / TABLE2_NAME}")
        print(f"Table3 saved to: {tables_dir / TABLE3_NAME}")
    print(f"JSON file saved to: {json_path}")
    print(f"CSV file saved to: {csv_path}")
    print(f"Missing coverage JSON saved to: {missing_json_path}")
    print(f"Missing coverage CSV saved to: {missing_csv_path}")
    print(f"Missing record count: {len(missing_records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
