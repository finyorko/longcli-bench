This document involves two major tasks. The first task is to modify the terminal-bench framework according to the following specification:
## Terminal Bench — long_cli Mode Step-by-Step Requirements Specification

This document is the authoritative design spec "chapter by chapter" by requirements. It is for engineering implementation and acceptance. It does not include historical commit notes. It includes the required installation and image build acceptance steps. All fields, file naming, directory structures, and statistics definitions follow this document.

### General Conventions and Terms
- Container working directory: `/app`
- Unified test output directory: `/app/test_output` (all tests, scores, metrics, Agent outputs, and instructions are written here)
- Two test tracks:
  - f2p (fail->pass): originally failing, should pass after Agent changes; represents "fix correctness".
  - p2p (pass->pass): originally should pass, Agent must not break; represents "steady-state no regression".
- Two parsing strategies:
  - pytest: framework parses pytest text output to get pass results and scores.
  - text: task self-evaluates; tests write `is_pass/step_score` into `<kind>_score.json`, framework only reads and aggregates.
- Numeric conventions:
  - `<kind>_is_pass`: all pass => 1; not all pass => 0; missing/unavailable => -1 (only for matrix padding).
  - `<kind>_step_score`: pass rate (0~1), keep 3 decimals (round to 3 decimal places). Missing/unavailable => -1.0 (only for matrix padding).
  - `agent_duration_time`: seconds, keep 1 decimal.
  - `parser_total_tokens`: integer; only attempt to parse when Agent=codex; if cannot parse or not codex, set to 0.
- `<kind>` is fixed to `f2p` or `p2p`.
- Multi-turn (turn): only effective when `parser_name=long_cli` and `--give-test-output N` is enabled; turns from 1..N. If not set, equivalent to single turn (N=1). In single turn, test artifacts are also moved to files with suffix `*_turn1`.
- Multi-attempt (attempt): when CLI uses `--n-attempts=M`, attempts from 1..M.

### Terminal-Bench Installation and CLI Availability (Required)
#### Goal
Ensure that Terminal-Bench can still be installed successfully after modifications and provides a working CLI (`tb`/`terminal-bench`), avoiding "code runs but cannot install / cannot call CLI".

#### Installation Convention
- Enter the terminal-bench folder and install terminal-bench:
  - Recommended: `uv pip install -e .`
  - Compatible: `uv run pip install -e .` or `pip install -e .`

All later acceptance commands default to using `tb ...`; if `command not found: tb` appears, it fails installation acceptance and you must fix entry points/PATH/environment first.
#### Acceptance Criteria
- Install command exit code is 0;
- `python -c "import terminal_bench"` exit code is 0;
- `tb --help` and `terminal-bench --help` both run successfully (exit code 0).

### Docker Image Build: `tb/codex52:v0` (Required)
#### Goal
Install docker.
Build `long_cli_dockerImage/Dockerfile.python-uv-pytest` as `tb/python-uv-pytest:2025-10-29`
And build `long_cli_dockerImage/Dockerfile.codex52` into a local Docker image: `tb/codex52:v0`.

#### Conventions
- This step runs on the host machine (requires Docker Engine running), not inside the task container.
- Only require build success and existence of `tb/codex52:v0`; no requirement to `docker save` export tar (do so only if you need offline distribution).

### Codex Install Script Modification

This project's Docker image already preinstalls Codex CLI, so the framework's "install codex" script should not perform any installation to avoid duplicate installs.
So you need to simplify the Codex install script to only print one line and remain executable, output must be `echo "Codex has been installed, execute directly."`, with no other installation logic. Ensure the file has no more than 3 lines.

### parser_name=long_cli and f2p/p2p Dual Test Parsing
#### Goal
Within a single task, support two test tracks (f2p and p2p) and choose a parsing strategy (pytest or text) for each. All test artifacts go under `/app/test_output`; the framework aggregates `<kind>_is_pass` and `<kind>_step_score` (and optional mappings) based on the strategy.

#### task.yaml Definition (Already in tasks)
- Required (relevant to this requirement):
  - `parser_name: long_cli`
  - `parser_results_f2p: pytest | text | null` (`null` means no f2p test set)
  - `parser_results_p2p: pytest | text | null` (`null` means no p2p test set)

Example (task.yaml snippet)
```yaml
instruction: |-
  Follow INSTRUCTION.md and fix the bug without breaking correct behavior.
parser_name: long_cli
parser_results_f2p: pytest
parser_results_p2p: text
max_agent_timeout_sec: 360
max_test_timeout_sec: 300
```

#### Task Directory and Runner Conventions
- `/tests/run-tests.sh`: task-provided test script (framework copies the task root `run-tests.sh` into container `/tests` and executes)
- `/tests/f2p.py`: pytest cases for f2p (if f2p uses pytest) or dependencies needed for text scoring script
- `/tests/p2p.py`: pytest cases for p2p (if p2p uses pytest) or dependencies needed for text scoring script
- Env var `TEST_DIR`: injected by docker-compose, defaults to `/tests` (scripts should use `$TEST_DIR`, avoid hardcoded paths).

#### Outputs (base names generated by task's run-tests.sh; turn suffix handled by framework)
- If `f2p=pytest`: `/app/test_output/f2p_output.txt`
- If `p2p=pytest`: `/app/test_output/p2p_output.txt`
- If `f2p=text`: `/app/test_output/f2p_output.txt` and `/app/test_output/f2p_score.json`
- If `p2p=text`: `/app/test_output/p2p_output.txt` and `/app/test_output/p2p_score.json`

#### Framework Parsing Rules (Framework Implementation)
- pytest strategy (framework parses `<kind>_output.txt` text and writes metrics):
  - `<kind>_is_pass`: 1 if all passed, else 0.
  - `<kind>_step_score`: pass rate, keep 3 decimals.
  - `<kind>_pytest_results`: value 1 for PASSED, 0 for FAILED; key is pytest function name (including parameterization).
  - Requirement: task pytest output must include pytest `short test summary info` (recommend `pytest -rA`), otherwise parser may not capture results.
- text strategy (task writes `<kind>_score.json`, framework reads and writes metrics):
  - Structure: `{"is_pass": 0|1, "step_score": 0.745}`
  - Framework normalizes step_score to 3 decimals (text path also follows "keep 3 decimals").

#### Single-turn metrics.json (Example)
Assume p2p parsing is pytest:
```json
{
  "f2p_is_pass": 1,
  "f2p_step_score": 0.342,
  "p2p_is_pass": 1,
  "p2p_step_score": 1.0,
  "p2p_pytest_results": {
    "test1": 1,
    "test2": 0
  }
}
```

#### Acceptance Criteria
- Support `parser_name=long_cli`.
- Support independent configuration of `pytest`, `text`, or `null` for f2p/p2p (null means no set, not parsed/scored).
- Artifacts are written to `/app/test_output`; field meanings and numeric conventions match; `step_score` kept to 3 decimals.

### Agent Duration and Token Stats (agent_duration_time / parser_total_tokens)
#### Goal
Attach agent execution duration and (for supported Agents) token usage parsing results to each turn's metrics.

#### Field Definitions (Per Turn)
- `agent_duration_time`: float, seconds, keep 1 decimal.
- `parser_total_tokens`: int, only attempt to parse when Agent=codex; if cannot parse or not codex, set to 0.

#### Parsing Rules
- Read `/app/test_output/agent_output_turn{T}.txt`, match pattern:
  - Text contains "tokens used" followed by a newline, next line is a number (may include thousands commas);
  - Or a number appears within 200 chars after "tokens used".
- Remove commas and convert to integer; if fails, set 0.

#### Turn Metrics Example
```json
{
  "agent_duration_time": 10.4,
  "parser_total_tokens": 4368,
  "f2p_is_pass": 1,
  "f2p_step_score": 1.0,
  "p2p_is_pass": 1,
  "p2p_step_score": 1.0
}
```

#### Acceptance Criteria
- Each turn writes `agent_duration_time`;
- When Agent=codex, `parser_total_tokens` can be parsed if output matches; failure does not affect flow (value 0).

### Multi-turn/Multi-attempt: per-turn and Aggregated Results, results.json Save
#### Goal
1. For `--give-test-output N` multi-turn results and `--n-attempts` 2D aggregation, unify description, and define Trial-level and Run-level results.json structure and fields. For each task, in Run-level results build a 2D matrix of "attempt x turn" and provide two aggregations: 1) `pass_in_kth`: raw record of each attempt's per-turn quadruple; 2) `pass_at_topk`: aggregate along attempts dimension up to current attempt (only attempts dimension, turns strictly aligned).
2. All test/score/metric artifacts must have `turn{T}` at end at turn end, to avoid next turn using previous artifacts; `agent_output.txt` is continuously written by tmux `tee`, but at each turn end must be copied to `agent_output_turn{T}.txt` for freezing and parsing.
3. Save appropriate fields into results.json, see details below.
4. If `--n-attempts` not set, it means `--n-attempts 1`.
5. If `--give-test-output` not set, it means `--give-test-output 1`.


#### /app/test_output Directory Structure Example
```
/app/test_output/
  agent_instruction_turn{T}.txt
  agent_output_turn{T}.txt
  # if f2p=pytest (pytest only has <kind>_output_turn{T}.txt)
  f2p_output_turn{T}.txt        
  # if p2p=text (text has <kind>_output_turn{T}.txt and <kind>_score_turn{T}.json)
  p2p_output_turn{T}.txt
  p2p_score_turn{T}.json
  metrics_turn{T}.json          
  ...
```
Meanwhile, the framework exports container `/app/test_output` to host trial output dir: `runs/<run_id>/<task_id>/<trial_name>/test_output/`, for acceptance and file comparison (host side usually keeps only `*_turn{T}` to avoid base name cross-turn contamination).

#### Quadruple Fields and Padding Rules
- `f2p_is_pass`: 1|0|-1
- `f2p_step_score`: >=0 or -1.0
- `p2p_is_pass`: 1|0|-1
- `p2p_step_score`: >=0 or -1.0

#### Aggregation Rules
(Based on per-turn metrics, e.g. `metrics_turn{T}.json` / `long_cli_test_turns`) If different attempts have different turn lengths, align to max turns within the task and pad missing with -1/-1.0.
- Normative definitions:
  - `pass_in_kth[a][t]`: only records the raw quadruple of turn t+1 in attempt a+1.
  - `pass_at_topk[a][t]`: only aggregates along attempts dimension, turns aligned:
    - `<kind>_is_pass`: if any of the first k attempts has 1 on this turn, then 1; otherwise 0; if this turn missing then -1.
    - `<kind>_step_score`: max score among first k attempts for this turn (if no valid score, -1.0). Aggregated score also normalized to 3 decimals.
- Equivalent rules:
  - `<kind>_is_pass`: if any 1 exists then 1; else if any 0 exists then 0; else -1.
  - `<kind>_step_score`: max of valid scores (>=0); if none, -1.0; then normalize to 3 decimals.
- Example formula:
  - `pass_at_topk[2][2][<kind>_step_score] = max(pass_in_kth[0][2][<kind>_step_score], pass_in_kth[1][2][<kind>_step_score], pass_in_kth[2][2][<kind>_step_score])`

#### Run-level Structure
```json
"long_cli_n_attempts": {
  "<task_id>": {
    "pass_in_kth": [  
      [ {quadruple_turn1}, {quadruple_turn2}, ... ],
      [ {…}, {…}, ... ],
      ...
    ],
    "pass_at_topk": [  
      [ {turn1_agg}, {turn2_agg}, ... ],
      [ {…}, {…}, ... ],
      ...
    ]
  },
  "<task_id_2>": { ... }
}
```

#### Example (Matches Expected)
```json
"long_cli_n_attempts": {
  "task1": {
    "pass_in_kth": [
      [
        {"f2p_is_pass": 0,"f2p_step_score": 0.0,"p2p_is_pass": -1,"p2p_step_score": -1.0},
        {"f2p_is_pass": 0,"f2p_step_score": 0.0,"p2p_is_pass": -1,"p2p_step_score": -1.0},
        {"f2p_is_pass": 0,"f2p_step_score": 0.0,"p2p_is_pass": -1,"p2p_step_score": -1.0}
      ],
      [
        {"f2p_is_pass": 0,"f2p_step_score": 0.0,"p2p_is_pass": -1,"p2p_step_score": -1.0},
        {"f2p_is_pass": 0,"f2p_step_score": 0.0,"p2p_is_pass": -1,"p2p_step_score": -1.0},
        {"f2p_is_pass": 0,"f2p_step_score": 0.0,"p2p_is_pass": -1,"p2p_step_score": -1.0}
      ]
    ],
    "pass_at_topk": [
      [
        {"f2p_is_pass": 0,"f2p_step_score": 0.0,"p2p_is_pass": -1,"p2p_step_score": -1.0},
        {"f2p_is_pass": 0,"f2p_step_score": 0.0,"p2p_is_pass": -1,"p2p_step_score": -1.0},
        {"f2p_is_pass": 0,"f2p_step_score": 0.0,"p2p_is_pass": -1,"p2p_step_score": -1.0}
      ],
      [
        {"f2p_is_pass": 0,"f2p_step_score": 0.0,"p2p_is_pass": -1,"p2p_step_score": -1.0},
        {"f2p_is_pass": 0,"f2p_step_score": 0.0,"p2p_is_pass": -1,"p2p_step_score": -1.0},
        {"f2p_is_pass": 0,"f2p_step_score": 0.0,"p2p_is_pass": -1,"p2p_step_score": -1.0}
      ]
    ]
  }
}
```

#### Flattened Text long_cli_n_attempts_compact
- Run-level results should also include `long_cli_n_attempts_compact` (a JSON object isomorphic to `long_cli_n_attempts`) for "readable layout":
  - Each task contains `pass_in_kth` and `pass_at_topk` keys;
  - Values are still 2D arrays, but require "one attempt per line" (each outer element / attempt row serialized as a single-line JSON array), for quick review and file diff;
  - Semantics must be identical to `long_cli_n_attempts`, only formatting differs.

Meaning: make viewing easier, because the default saved json file stores one entry per line. This step provides a readable data view, putting all elements of the 2D array on one line (i.e., one attempt per line).

#### Index Semantics
- `BenchmarkResults["long_cli_n_attempts"][task_id]["pass_in_kth"][m][n]` means "in task task_id, the quadruple result of turn n+1 in attempt m+1".

#### Agent Output and Per-Turn Instructions
- Per-turn instruction file: `/app/test_output/agent_instruction_turn{T}.txt`
  - Write time: written by framework before executing Agent each turn (must be written even if `TB_SKIP_AGENT=1`, for playback/compare).
  - Turn=1: content must exactly match `task.yaml: instruction` (no extra context).
  - Turn>=2 and `parser_name=long_cli`: append "iterative fix context block" after the original instruction (for multi-turn dialogue), controlled by `TB_LONG_CLI_TEST_OUTPUT_MODE`:
    - **Default `path` mode** (`TB_LONG_CLI_TEST_OUTPUT_MODE` in {`path`,`paths`,`file`,`files`}): only provide previous test output file paths (stable, comparable).
    - **`inline` mode** (other values, e.g. `inline`): inline previous test output raw text with fixed markers (so model can read output directly).

##### Exact Concatenation Template for `agent_instruction_turn{T}.txt` (for acceptance/file comparison)
In templates below, `{ORIG}` is original instruction (`task.yaml: instruction`), `T` is current turn (starting at 1), `N` is total turns (`--give-test-output N`; if not set N=1), `P=T-1`.

**A) `path` mode (default)**
```
{ORIG}

Context: Iterative test-fix loop (turn T/N).
Previous test outputs are saved in the container:
- Fail-to-pass (f2p) output file: /app/test_output/f2p_output_turnP.txt
- Pass-to-pass (p2p) output file: /app/test_output/p2p_output_turnP.txt

Required action:
- If outputs already satisfy acceptance criteria, make no changes.
- Otherwise, minimally revise the code to satisfy failing tests.
Constraints:
- Prefer smallest viable edits and preserve passing behavior.
- Do not modify test files.
- Keep changes clear; add comments only when essential.
```

**B) `inline` mode (optional)**
```
{ORIG}

Context: Iterative test-fix loop (turn T/N).
Previous test outputs:
- Fail-to-pass (f2p) raw output:
<<BEGIN_F2P[P]>>
{F2P_TEXT}
<<END_F2P[P]>>
- Pass-to-pass (p2p) raw output:
<<BEGIN_P2P[P]>>
{P2P_TEXT}
<<END_P2P[P]>>

Required action:
- If outputs already satisfy acceptance criteria, make no changes.
- Otherwise, minimally revise the code to satisfy failing tests.
Constraints:
- Prefer smallest viable edits and preserve passing behavior.
- Do not modify test files.
- Keep changes clear; add comments only when essential.
```
Placeholder rules:
- If previous turn did not capture f2p output text, `{F2P_TEXT}` must be literal: `<no f2p output captured>`
- If previous turn did not capture p2p output text, `{P2P_TEXT}` must be literal: `<no p2p output captured>`
- Agent stdout: continuously written to base name `/app/test_output/agent_output.txt` via tmux `tee`; at end of turn copy to `/app/test_output/agent_output_turn{T}.txt` (used for later parsing, output text will strip ANSI). When `TB_SKIP_AGENT=1`, Agent is not executed; this turn uses placeholder command output:
  - `echo "TB_SKIP_AGENT=1, skip agent exec"`
  This output is saved by `tee` into `agent_output_turn{T}.txt` just like normal. Do not change this literal (used for playback/search).
  - Important: before each turn, you must "clear but not delete" `/app/test_output/agent_output.txt` (recommend `: > /app/test_output/agent_output.txt`), to avoid cross-turn accumulation; do not `rm` this file in container (tmux `tee` keeps file descriptor; unlink may lead to unexpected writes).


#### Test Artifacts Base Name -> Generated Turn-Suffixed Files (Framework Responsible)
- Happens inside container at each turn end (to avoid leftover being misread in next turn).
- Move base names to:
  - `f2p_output_turn{T}.txt`, `p2p_output_turn{T}.txt` (pytest)
  - `f2p_score_turn{T}.json`, `p2p_score_turn{T}.json` (text)
  - `metrics_turn{T}.json` (if task wrote base name `metrics.json`, it is also frozen to this file name at turn end; framework also generates/overwrites `metrics_turn{T}.json` on host as per-turn metrics snapshot)
- Explicit move coverage (if exists then move): `f2p_output.txt`, `p2p_output.txt`, `f2p_score.json`, `p2p_score.json`, `metrics.json`.
- After move, delete base names.
- Single-turn convention: if `--give-test-output` not set, still move to `*_turn1`, ensuring no residue across turns/stages.

#### Multi-turn Goal (give-test-output)
When CLI uses `--give-test-output N`, within each attempt execute N turns without early stop; each turn feeds previous test output back into next turn instruction (default `path` mode provides file paths; `inline` mode embeds raw text); all base name artifacts (under /app/test_output) are moved to turn-suffixed files at turn end to avoid cross-turn interference; trial-level artifacts include per-turn metrics sequence (e.g., <kind>_output.txt -> <kind>_output_turn{T}.txt); run-level artifacts include 2D matrix (task -> [attempt][turn]).

#### Per-turn Flow (T=1..N)
1) Write `/app/test_output/agent_instruction_turn{T}.txt`
2) Execute Agent; if `TB_SKIP_AGENT=1`, execute placeholder output:
   - `echo "TB_SKIP_AGENT=1, skip agent exec"`
   This output is written by tmux `tee` to `/app/test_output/agent_output.txt` and copied at end of turn to `/app/test_output/agent_output_turn{T}.txt`. Do not change this literal (used for playback/search).
3) Execute `run-tests.sh`, task only writes base name artifacts (pytest: `<kind>_output.txt`; text: `<kind>_output.txt` + `<kind>_score.json`)
4) Framework moves base names to `*_turn{T}` in container and deletes base names
5) Parse this turn's metrics and append to trial's `long_cli_test_turns`

#### results.json Save
##### Trial-level result fields (`runs/<run_id>/<task_id>/<trial_name>/results.json`)
- `long_cli`: dict, equals turn1 metrics (baseline snapshot), i.e. long_cli_test_turns[0]
- `long_cli_test_turns`: list[dict], per-turn metrics for turn1..turnN
- `is_resolved`: bool, in long_cli defined as "there exists a turn that meets pass criteria", and pass criteria depends on task.yaml config:
  - If both `parser_results_f2p` and `parser_results_p2p` are `null`: always false
  - If only one is configured (`pytest` or `text`): there exists a turn where that `<kind>_is_pass=1`
  - If both are configured (`pytest` or `text`): there exists a turn where both `f2p_is_pass=1` and `p2p_is_pass=1`
- `resolved_turn_index`: int|None, 1-based index of first turn that meets pass criteria

Trial-level snippet example:
```json
{
  "long_cli": {
    "agent_duration_time": 9.8,
    "parser_total_tokens": 4321,
    "f2p_is_pass": 0,
    "f2p_step_score": 0.5,
    "p2p_is_pass": 1,
    "p2p_step_score": 1.0
  },
  "long_cli_test_turns": [
    {"agent_duration_time": 9.8, "parser_total_tokens": 4321, "f2p_is_pass": 0, "f2p_step_score": 0.5, "p2p_is_pass": 1, "p2p_step_score": 1.0},
    {"agent_duration_time": 10.1, "parser_total_tokens": 4100, "f2p_is_pass": 1, "f2p_step_score": 1.0, "p2p_is_pass": 1, "p2p_step_score": 1.0},
    {"agent_duration_time": 10.7, "parser_total_tokens": 4050, "f2p_is_pass": 1, "f2p_step_score": 1.0, "p2p_is_pass": 1, "p2p_step_score": 1.0}
  ],
  "resolved_turn_index": 2,
  "is_resolved": true
}
```

##### Run-level: `long_cli_all_results` (2D, task -> [attempt][turn])
Run-level aggregated results file path: `runs/<run_id>/results.json`
```json
"long_cli_all_results": {
  "task1": [
    [ {turn1_dict}, {turn2_dict}, {turn3_dict} ],
    [ {turn1_dict}, {turn2_dict}, {turn3_dict} ]
  ],
  "task2": []
}
```

#### Acceptance Criteria (Aggregation/Multi-turn/Save)
- Run-level artifacts include `long_cli_n_attempts` and `long_cli_n_attempts_compact`;
- Turn alignment aggregation correct, tail padding correct;
- `*_turn{T}` files correspond one-to-one with `long_cli_test_turns` content;
- `long_cli_all_results` shape is task -> [attempt][turn];
- long_cli `is_resolved` and `resolved_turn_index` meet definitions (consider f2p/p2p = `null`).

### Environment Variables and Output Collection (TB_SKIP_AGENT, TB_SAVE_APP_RESULT, etc.)
#### Goal
Provide unified switches for debugging and ensure Agent output, per-turn instructions, and test artifacts are reliably collected to `/app/test_output`.

#### Environment Variables
- `TB_SKIP_AGENT`: skip Agent execution (1/true/True). Still runs all turns of tests and writes to disk; Agent instructions and per-turn placeholder output are still written. Placeholder output is fixed:
  - `echo "TB_SKIP_AGENT=1, skip agent exec"`
  This output is captured by tmux `tee` to `/app/test_output/agent_output.txt` and copied to `/app/test_output/agent_output_turn{T}.txt` at end of each turn. Do not change this literal (for playback/search).
- `TB_SAVE_APP_RESULT`: capture container `/app` directory to trial output dir `app_result/`.
- `TB_LONG_CLI_TEST_OUTPUT_MODE`: controls how previous turn test output is presented in `agent_instruction_turn{T}.txt` for turn>=2:
  - Value in {`path`,`paths`,`file`,`files`}: `path` mode (default), only provides previous output file paths;
  - Other values (e.g. `inline`): `inline` mode, embeds previous raw output in instruction (wrapped by `<<BEGIN_F2P[P]>>`/`<<END_F2P[P]>>`, `<<BEGIN_P2P[P]>>`/`<<END_P2P[P]>>`).
- `TB_TURN_IDX`: read-only env var injected by framework when executing `run-tests.sh` (string, 1-based), indicating current turn; tasks can use it to generate turn-related output (e.g., debug info).


#### Acceptance Criteria
- With `TB_SKIP_AGENT=1`, Agent execution is skipped, but N-turn testing and write-to-disk flow is intact; instructions and `*_turn{T}` files exist.
- With `TB_SAVE_APP_RESULT=1`, each trial ends with `app_result/` snapshot; errors are non-fatal.

### Appendix A: Field and File Name Mapping
- Task-side output (base names)
  - pytest: `f2p_output.txt`, `p2p_output.txt`
  - text: `f2p_output.txt`, `f2p_score.json`, `p2p_output.txt`, `p2p_score.json`
- Framework-moved files (with turn suffix)
  - `f2p_output_turn{T}.txt`, `p2p_output_turn{T}.txt`
  - `f2p_score_turn{T}.json`, `p2p_score_turn{T}.json`
  - `metrics_turn{T}.json` (generated each turn by framework; if task writes `metrics.json`, it is also frozen to this file name at turn end)
- Agent-related
  - `agent_instruction_turn{T}.txt` (instructions to agent each turn)
  - `agent_output_turn{T}.txt` (output of agent execution each turn)
- Trial-level result fields
  - `long_cli` (turn1 snapshot)
  - `long_cli_test_turns` (per-turn list)
  - `is_resolved` / `resolved_turn_index`
  - `total_input_tokens` / `total_output_tokens` (if Agent provides)
- Run-level result fields
  - `long_cli_all_results`: task -> [attempt][turn] -> turn metrics dict
  - `long_cli_n_attempts`: task -> {`pass_in_kth`, `pass_at_topk`}
  - `long_cli_n_attempts_compact`: flattened text view, shows pass_in_kth and pass_at_topk

Example, part of bench results.json with --n-attempts 2 --give-test-output 2, showing long_cli_n_attempts and long_cli_n_attempts_compact:
```
{   
    "id": "id",
    "results": [],
    "long_cli_all_results": {},
    "long_cli_n_attempts": {
        "pytest_text": {
            "pass_in_kth": [
                [
                    {
                        "f2p_is_pass": 1,
                        "f2p_step_score": 1.0,
                        "p2p_is_pass": 1,
                        "p2p_step_score": 1.0
                    },
                    {
                        "f2p_is_pass": 1,
                        "f2p_step_score": 1.0,
                        "p2p_is_pass": 0,
                        "p2p_step_score": 0.0
                    }
                ],
                [
                    {
                        "f2p_is_pass": 1,
                        "f2p_step_score": 1.0,
                        "p2p_is_pass": 1,
                        "p2p_step_score": 1.0
                    },
                    {
                        "f2p_is_pass": 1,
                        "f2p_step_score": 1.0,
                        "p2p_is_pass": 0,
                        "p2p_step_score": 0.0
                    }
                ]
            ],
            "pass_at_topk": [
                [
                    {
                        "f2p_is_pass": 1,
                        "f2p_step_score": 1.0,
                        "p2p_is_pass": 1,
                        "p2p_step_score": 1.0
                    },
                    {
                        "f2p_is_pass": 1,
                        "f2p_step_score": 1.0,
                        "p2p_is_pass": 0,
                        "p2p_step_score": 0.0
                    }
                ],
                [
                    {
                        "f2p_is_pass": 1,
                        "f2p_step_score": 1.0,
                        "p2p_is_pass": 1,
                        "p2p_step_score": 1.0
                    },
                    {
                        "f2p_is_pass": 1,
                        "f2p_step_score": 1.0,
                        "p2p_is_pass": 0,
                        "p2p_step_score": 0.0
                    }
                ]
            ]
        }
    },
    "long_cli_n_attempts_compact": {
        "pytest_text": {
            "pass_in_kth": [
                [{"f2p_is_pass": 1,"f2p_step_score": 1.0,"p2p_is_pass": 1,"p2p_step_score": 1.0},{"f2p_is_pass": 1,"f2p_step_score": 1.0,"p2p_is_pass": 0,"p2p_step_score": 0.0}],
                [{"f2p_is_pass": 1,"f2p_step_score": 1.0,"p2p_is_pass": 1,"p2p_step_score": 1.0},{"f2p_is_pass": 1,"f2p_step_score": 1.0,"p2p_is_pass": 0,"p2p_step_score": 0.0}]
            ],
            "pass_at_topk": [
                [{"f2p_is_pass": 1,"f2p_step_score": 1.0,"p2p_is_pass": 1,"p2p_step_score": 1.0},{"f2p_is_pass": 1,"f2p_step_score": 1.0,"p2p_is_pass": 0,"p2p_step_score": 0.0}],
                [{"f2p_is_pass": 1,"f2p_step_score": 1.0,"p2p_is_pass": 1,"p2p_step_score": 1.0},{"f2p_is_pass": 1,"f2p_step_score": 1.0,"p2p_is_pass": 0,"p2p_step_score": 0.0}]
            ]
        }
    },
}
```


## Execute Tasks Based on the Modified Framework

In the terminal-bench folder, execute the following tasks in order
```
TB_SKIP_AGENT=1 TB_SAVE_APP_RESULT=1 tb run \
--agent codex \
--model gpt-5.1 \
--task-id pytest_pytest_example \
--dataset-path tasks_long_cli \
--run-id pytest_pytest_example

TB_SKIP_AGENT=1 TB_SAVE_APP_RESULT=1 tb run \
--agent codex \
--model gpt-5.1 \
--task-id pytest_pytest_example_finished \
--dataset-path tasks_long_cli \
--run-id pytest_pytest_example_finished

TB_SKIP_AGENT=1 TB_SAVE_APP_RESULT=1 tb run \
--agent codex \
--model gpt-5.1 \
--task-id pytest_pytest_example_f2p \
--dataset-path tasks_long_cli \
--run-id pytest_pytest_example_f2p


TB_SKIP_AGENT=1 TB_SAVE_APP_RESULT=1 tb run \
--agent codex \
--model gpt-5.1 \
--n-attempts 1 \
--give-test-output 3 \
--task-id pytest_pytest_example \
--dataset-path tasks_long_cli \
--run-id pytest_pytest_example_1_3


TB_SKIP_AGENT=1 TB_SAVE_APP_RESULT=1 tb run \
--agent codex \
--model gpt-5.1 \
--n-attempts 3 \
--give-test-output 1 \
--task-id pytest_pytest_example \
--dataset-path tasks_long_cli \
--run-id pytest_pytest_example_3_1
```
