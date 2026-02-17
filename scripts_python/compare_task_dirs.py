#!/usr/bin/env python3
import hashlib
import os
from pathlib import Path

# Update this list with your folder pairs (left_dir, right_dir).
# Paths are relative to the repo root by default.
PAIRS = [
        ("tasks_long_cli/61810_cow", "tasks_long_cli_finished/61810_cow_81"),
        ("tasks_long_cli/61810_fs", "tasks_long_cli_finished/61810_fs_finished"),
        ("tasks_long_cli/61810_lock", "tasks_long_cli_finished/61810_lock_71"),
        ("tasks_long_cli/61810_mmap", "tasks_long_cli_finished/61810_mmap_121"),
        ("tasks_long_cli/61810_net", "tasks_long_cli_finished/61810_net_finished"),
        ("tasks_long_cli/61810_pgtbl", "tasks_long_cli_finished/61810_pgtbl_36"),
        ("tasks_long_cli/61810_syscall", "tasks_long_cli_finished/61810_syscall_finished"),
        ("tasks_long_cli/61810_thread", "tasks_long_cli_finished/61810_thread_finished"),
        ("tasks_long_cli/61810_traps", "tasks_long_cli_finished/61810_traps_76"),
]

OUTPUT_PATH = "compare_task_dirs_output.txt"

IGNORE_FILES = {"tasks.yaml", "task.yaml", "Dockerfile", "run-tests.sh", ".gitignore"}
IGNORE_DIRS = {"tests", "__pycache__"}
IGNORE_EXTS = {".png", ".js"}


def is_out_artifact(name: str) -> bool:
    return name.endswith(".out") or ".out." in name


def should_ignore(rel_path: Path, is_dir: bool) -> bool:
    parts = rel_path.parts
    if any(part in IGNORE_DIRS for part in parts):
        return True
    if not is_dir:
        if rel_path.name.startswith("_"):
            return True
        if rel_path.name in IGNORE_FILES:
            return True
        if rel_path.suffix.lower() in IGNORE_EXTS:
            return True
        if is_out_artifact(rel_path.name):
            return True
    return False


def collect_files(base_dir: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for root, dirs, filenames in os.walk(base_dir):
        rel_root = Path(root).relative_to(base_dir)

        # Prune ignored directories in-place so os.walk does not descend.
        kept_dirs = []
        for dname in dirs:
            rel_dir = rel_root / dname if rel_root != Path(".") else Path(dname)
            if should_ignore(rel_dir, is_dir=True):
                continue
            kept_dirs.append(dname)
        dirs[:] = kept_dirs

        for fname in filenames:
            rel_file = rel_root / fname if rel_root != Path(".") else Path(fname)
            if should_ignore(rel_file, is_dir=False):
                continue
            files[str(rel_file)] = Path(root) / fname
    return files


def file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def compare_dirs(left_dir: Path, right_dir: Path) -> tuple[list[str], list[str], list[str]]:
    left_files = collect_files(left_dir)
    right_files = collect_files(right_dir)

    left_set = set(left_files)
    right_set = set(right_files)

    only_left = sorted(left_set - right_set)
    only_right = sorted(right_set - left_set)

    different = []
    for rel_path in sorted(left_set & right_set):
        left_path = left_files[rel_path]
        right_path = right_files[rel_path]
        if left_path.stat().st_size != right_path.stat().st_size:
            different.append(rel_path)
            continue
        if file_hash(left_path) != file_hash(right_path):
            different.append(rel_path)

    return only_left, only_right, different


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    had_error = False
    output_lines = []

    for left, right in PAIRS:
        left_path = (repo_root / left).resolve()
        right_path = (repo_root / right).resolve()

        output_lines.append("===")
        output_lines.append(f"Pair: {left} <> {right}")

        if not left_path.exists() or not right_path.exists():
            output_lines.append("Missing directory:")
            if not left_path.exists():
                output_lines.append(f"  - {left_path}")
            if not right_path.exists():
                output_lines.append(f"  - {right_path}")
            had_error = True
            continue

        only_left, only_right, different = compare_dirs(left_path, right_path)

        if not only_left and not only_right and not different:
            output_lines.append("No differences.")
            continue

        if only_left:
            output_lines.append("Only in left:")
            for item in only_left:
                output_lines.append(f"  - {item}")
        if only_right:
            output_lines.append("Only in right:")
            for item in only_right:
                output_lines.append(f"  - {item}")
        if different:
            output_lines.append("Different content:")
            for item in different:
                output_lines.append(f"  - {item}")

    output_path = repo_root / OUTPUT_PATH
    output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    print(f"Wrote report to: {output_path}")
    return 1 if had_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
