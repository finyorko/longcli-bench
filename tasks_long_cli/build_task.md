## Build LongCLI-Bench Long-Chain Tasks

### Prerequisites

- Prerequisite: Docker, Python, and `uv` are installed; `tb` is installed and callable.

### Task Requirements

Collected tasks include the following categories:

1. Project setup (`from_scratch`): "from 0 to 1". Evaluates an Agent's ability to plan, configure, and build a runnable project from scratch.
2. Feature implementation (`feature_add`): "from N to N+1". Evaluates an Agent's ability to add new modules or features in an existing codebase.
3. Bug fixing (`bug_fix`): "from N (No) to N (Yes)". Evaluates an Agent's ability to diagnose, locate, and fix complex bugs.
4. Project refactoring (`project_refactor`): "from N (A) to N (B)". Evaluates an Agent's ability to optimize, migrate, or adjust code structure without changing external behavior.

Task workflow: provide an initial codebase directory (if implementing from scratch, it can be empty), give the requirement to a terminal agent, and let the terminal agent directly operate on the codebase to fulfill the requirement.

Task sources come from real long-chain tasks encountered in daily work through frequent interactions with ChatGPT and similar tools, such as implementing framework features or pipeline flows. Coding models usually cannot complete these in a single attempt. For example, while constructing a dataset, there may be a full process from raw data cleaning to structuring. You can use the full process requirements as the task prompt, and have the agent generate/modify code to complete it.

### Template Overview (`tasks_long_cli_example/task_template`)

#### Directory Structure

```plain
├── Dockerfile          # Install the environment needed to run the task; default includes Python runtime. Modify if extra dependencies are required.
├── INSTRUCTION.md      # Define the full detailed task chain; this is passed to the model as the requirement.
├── docker-compose.yaml # Usually no need to modify.
├── run-tests.sh        # Objective test script; you need to implement this.
├── solution.sh         # Usually no need to modify.
├── task.yaml           # Task metadata file; update score parsing modes for the two test sets.
├── task_dir            # Task folder; can be renamed, but update Dockerfile accordingly.
└── tests               # Test folder; update files below. You may add more test files, but scoring must be based on these files.
    ├── f2p.py
    ├── p2p.py
    └── score_utils.py
```

- Directory structure and purpose
  - `Dockerfile`: Builds the task image.
    - Copies **task** resources (`task_dir/`, `INSTRUCTION.md`).
    - You need to add: system dependencies, runtime environment setup, etc.
  - `docker-compose.yaml`: Environment variables and mounts are filled by the framework; usually no change needed.
    - Key point: `TEST_DIR=${T_BENCH_TEST_DIR}` mounts `tests/` into the container (usually as `/tests`) and uses it via `$TEST_DIR` in `run-tests.sh`.
    - Note: you do **not** need to copy `tests/` in Dockerfile.
  - `task.yaml`: Task metadata (parser mode, timeout, tags, etc.).
    - Common fields (consistent with `LONG_CLI_READMD.md`):
      - `instruction`: instruction text passed to the agent (can point to `INSTRUCTION.md`).
      - `parser_name`: fixed as `long_cli`.
      - `parser_results_f2p` / `parser_results_p2p`: parsing mode for each test set: `pytest`, `text`, or `null` (no such test set). If `null`, that set is excluded from parsing/scoring, and corresponding keys are omitted from result files.
      - `category`: choose one from `from_scratch/feature_add/bug_fix/project_refactor`.
      - `tags`: arbitrary tags, e.g. system/python/java/data-filter, describing the task domain.
      - `max_agent_timeout_sec`: agent timeout in seconds. Simple tasks: 300-900; complex projects can be higher.
  - `INSTRUCTION.md`: task description and acceptance criteria. If implementing a new feature, define program entry points and test output format clearly to make testing easier.
  - `run-tests.sh`: test script automatically executed in the container. You must modify it so outputs are saved under `/app/test_output`.
    - Required: `mkdir -p /app/test_output`; ensure each kind (`f2p`/`p2p`) generates `<kind>_output.txt`; text mode also needs `<kind>_score.json`.
    - Parser mode comparison:
      - pytest: `uv run pytest "$TEST_DIR/<kind>.py" -rA > /app/test_output/<kind>_output.txt 2>&1`
      - text: run `uv run python "$TEST_DIR/<kind>.py"` to parse and write scores (read `/app/test_output/<kind>_output.txt` and write `/app/test_output/<kind>_score.json`).
  - `tests/`:
    - `f2p.py`, `p2p.py`:
      - Pytest mode: regular pytest cases and assertions; mark non-scoring cases with `@pytest.mark.skip`. In `run-tests.sh`, save output using `uv run pytest "$TEST_DIR/<kind>.py" -rA > /app/test_output/<kind>_output.txt 2>&1`.
      - Text mode: first generate `/app/test_output/<kind>_output.txt` in `run-tests.sh`; then run `uv run python "$TEST_DIR/<kind>.py"`, read `/app/test_output/<kind>_output.txt`, parse `is_pass` and `step_score`, and call `write_score_auto(is_pass, step_score)`. This function automatically saves `/app/test_output/<kind>_score.json`.
    - `score_utils.py`: `write_score_auto` / `write_score_json` are already implemented; `write_score_auto` is recommended.
  - `task_dir/`: task assets (code/data/etc.); copy to `/app/task_dir/` or other path in `Dockerfile`.
  - `solution.sh`: can be empty; used for interactive debugging/demo.

- Placeholders and Notes
  - Replace all `<kind>` placeholders in the template with either `f2p` or `p2p`; do not mix.
  - All required edit points are marked with `#TODO`.
  - All outputs must be under `/app/test_output`; filenames must be exactly `<kind>_output.txt` and (for text mode) `<kind>_score.json`.
  - `is_pass` only takes 0/1; 1 means all tasks passed or full score.
  - `step_score` is recommended to be normalized to [0.0, 1.0], representing percentage score, with three significant digits.

- Each major task must provide **two task codebases** (in practice, different `task_dir` folders; all other content is the same):
  - Initial directory: unmodified codebase files. Can be named `<task_id>`.
  - Completed directory: the final implemented codebase. Can be named `<task_id>_finished`.

#### Mapping Between `task_template` and Container Paths

- `INSTRUCTION.md` maps to `/app/INSTRUCTION.md` in the container.
- `task_dir` maps to `/app/task_dir` in the container.
- `run-tests.sh` maps to `/tests/run-tests.sh` in the container.
- `tests/<kind>.py` maps to `/tests/<kind>.py` in the container.

### Two Parsing Modes

#### Pytest Parsing Mode

This mode fits cases where each sub-feature can be split and verified by functions. The framework automatically computes `is_pass` and `step_score` from the number of correctly executed functions. For pytest mode, `run-tests.sh` only needs to run pytest on `tests/<kind>.py` and save output to `/app/test_output/<kind>_output.txt`, usually with one line in `run-tests.sh`:

```bash
uv run pytest "/tests/<kind>.py" -rA > /app/test_output/<kind>_output.txt 2>&1
```

In `tests/<kind>.py`, write `assert` checks in test functions to determine whether features are implemented correctly.

##### Files Required by Pytest Mode

```plain
/app/test_output/<kind>_output.txt
```

#### Text Parsing Mode

This mode fits cases where splitting features is inconvenient and you need to compute scores manually. For text mode, `run-tests.sh` should write scoring output to `/app/test_output/<kind>_output.txt`, then you and `tests/<kind>.py` parse it into `<kind>_score.json`.

For example: initial score is 20 and full score is 100. You define a scoring rule that gives 85. Then `is_pass=0, step_score=(85 - 20)/(100 - 20)`. The score 85 is extracted by `<kind>.py` from `/app/test_output/<kind>_output.txt`.

Assume `kind=f2p`:

```shell
(
  # Pre-steps
  # ...
  # Save to f2p_output.txt
  <your command> | tee /app/test_output/f2p_output.txt
)
# f2p.py parses /app/test_output/f2p_output.txt into two scores: is_pass and step_score
python3 "/app/tests/f2p.py"
```

##### Files Required by Text Mode

```plain
# Usually generated in run-tests.sh, can also be generated in /tests/<kind>.py
/app/test_output/<kind>_output.txt
# Written in /tests/<kind>.py via write_score_auto
/app/test_output/<kind>_score.json
```

### Quick Start to Build a Task (Using `text_pytest_example`)
> Note: You need two folders at the end, `<task_id>` and `<task_id>_finished`, representing initial and completed task folders.
> Test with this command: `TB_SKIP_AGENT=1 tb run --agent codex --model gpt-5 --task-id <task_id> --dataset-path tasks_long_cli`
> The initial folder should score 0, and the completed folder should score full marks.
>
> In actual task construction, place tasks under the **tasks_long_cli** folder.

The following steps show how to start from the template and build a task with `f2p=text, p2p=pytest`; you can compare with `tasks_long_cli_example/text_pytest_example`.

#### Modification Steps

##### Copy the Template

This project provides a task template at `tasks_long_cli_example/task_template`. Required edit points are marked with `#TODO`.

```bash
cp -r tasks_long_cli_example/task_template tasks_long_cli_example/text_pytest_example
```

##### Configure Parsing Modes (`task.yaml`, fill relevant parts)

```yaml
instruction: |-
  Open and follow the detailed project specification at INSTRUCTION.md. Implement the CS61A Hog project tasks accordingly in folder cs61-hog.
category: from_scratch
tags:
  - system
parser_name: long_cli
parser_results_f2p: text
parser_results_p2p: pytest
max_agent_timeout_sec: 3600.0
```

Notes:

- `instruction` should specify the directory where the model executes tasks, such as `cs61-hog`.

##### Write `Dockerfile`

- The task needs the `cs61-hog` directory. So copy it in `Dockerfile`:

```Dockerfile
FROM tb/python-uv-pytest:2025-10-29
WORKDIR /app
# Copy task directory
COPY cs61-hog ./cs61-hog
# Copy task description file
COPY INSTRUCTION.md ./INSTRUCTION.md
```

##### Write `INSTRUCTION.md`

- Guide the agent to complete specified tasks in `cs61-hog`; and (if needed) describe output format clearly so `run-tests.sh` and `/tests/<kind>.py` can parse reliably.

##### Write `run-tests.sh` (Generate Test Outputs)

- For text `f2p`: run ok tests, write text output to `/app/test_output/f2p_output.txt`, then call `tests/f2p.py` to parse and write `/app/test_output/f2p_score.json`.
- For pytest `p2p`: directly run pytest and write output to `/app/test_output/p2p_output.txt`.
Example (see `tasks_long_cli_example/text_pytest_example/run-tests.sh`):

```bash
mkdir -p /app/test_output

# f2p=text: run ok test and write f2p_output.txt
(
  cp -a "/tests/." "/app/cs61-hog/"   # Let the ok tool see tests
  cd "/app/cs61-hog/"
  # This is the scoring command; save its output to /app/test_output/f2p_output.txt
  python3 ok --local --score | tee /app/test_output/f2p_output.txt
)
# Parse /app/test_output/f2p_output.txt and call write_score_auto. In container, $TEST_DIR defaults to /tests
python3 "$TEST_DIR/f2p.py"

#########
# p2p=pytest: just write output to p2p_output.txt
uv run pytest "$TEST_DIR/p2p.py" -rA > /app/test_output/p2p_output.txt 2>&1
```

##### Write `tests/<kind>.py` (Scoring and Validation)

- `tests/f2p.py` (text scoring): read `f2p_output.txt`, extract `Score:  Total: <X>` by regex, compute `is_pass` and `step_score`, then call `write_score_auto`; this function auto-saves `f2p_score.json`. See `tasks_long_cli_example/text_pytest_example/tests/f2p.py`.

- `tests/p2p.py` (pytest validation): the example uses file MD5 checks to prevent unintended modifications to immutable resources; add additional functional tests as needed. See `tasks_long_cli_example/text_pytest_example/tests/p2p.py`.

Minimal pytest example:

```python
import pytest

def test_example():
    # Example only: replace with real project validation (file integrity / functional checks)
    assert 1 + 1 == 2

# Skip non-scoring tests with @pytest.mark.skip; failures will not be counted.
@pytest.mark.skip(reason="Development helper only, not scored")
def test_dev_helper_example():
    assert 1 + 1 == 2
```

##### Validate in Container (Without Running Agent)

Enter interactive container:

```bash
uv run tb tasks interact -t <task-id> --tasks-dir <task_dir> --include-all
```

Run inside container:

```bash
bash /tests/run-tests.sh
ls -la /app/test_output
```

Expected: `f2p_output.txt`, `f2p_score.json` (text mode), and `p2p_output.txt` exist, and content is correct.

##### Validate from CLI (Skip Agent Execution)

1. Test `<task-id>`; both `is_pass` and `step_score` should be 0.
```
TB_SKIP_AGENT=1 TB_SAVE_APP_RESULT=1 tb run \
  --agent codex \
  --model gpt-5 \
  --task-id <task-id> \
  --dataset-path tasks_long_cli
```
1. Test `<task-id>_finished`; both `is_pass` and `step_score` should be 1.
```
TB_SKIP_AGENT=1 TB_SAVE_APP_RESULT=1 tb run \
  --agent codex \
  --model gpt-5 \
  --task-id <task-id>_finished \
  --dataset-path tasks_parser_init
```

Expected: output is under `runs/text_pytest_example_run`, and `app_result/test_output` contains test files. Focus on checking `f2p_output_turn{T}.txt`, `f2p_score_turn{T}.json` (text mode), and `p2p_output_turn{T}.txt`. Also verify `metrics_turn{T}.json` exists (saved by the framework), including `f2p_is_pass`, `p2p_is_pass`, `step_score`, etc.
##### Checklist

- [ ] Dockerfile uses an available base image, and copies `INSTRUCTION.md` plus task directory.
- [ ] `task.yaml` fields are complete and consistent with parsing mode (`parser_name: long_cli`, f2p/p2p parser settings, category, tags, timeout, etc.).
- [ ] `run-tests.sh` generates `/app/test_output/<kind>_output.txt` for each kind; if text parser is used, it calls `uv run python "$TEST_DIR/<kind>.py"` to generate `<kind>_score.json`.
- [ ] `tests/<kind>.py`: pytest has proper assertion functions; text parser reads `<kind>_output.txt` and calls `write_score_auto`.
- [ ] Verified by entering container via interact (recommended with `--include-all`) and running `run-tests.sh` manually.
- [ ] Verified artifacts and metrics via `tb run` with `TB_SKIP_AGENT=1` (check `metrics_turn{T}.json` under `runs/<run-id>`).
- [ ] Two folders exist: `<task_id>` and `<task_id>_finished`.
