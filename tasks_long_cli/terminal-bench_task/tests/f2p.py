import json
from pathlib import Path


TEST_OUTPUT_DIR = Path("/app/test_output")
TB_ROOT = Path("/app/terminal-bench")
RUNS_DIR = TB_ROOT / "runs"
SKIP_MARKER = "TB_SKIP_AGENT=1, skip agent exec"


def _read_text(path: Path) -> str:
    assert path.exists(), f"Missing file: {path}"
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_json(path: Path) -> dict:
    return json.loads(_read_text(path))


def _status_code(name: str) -> int:
    path = TEST_OUTPUT_DIR / f"{name}.status"
    raw = _read_text(path).strip()
    assert raw, f"Empty status file: {path}"
    try:
        return int(raw)
    except ValueError as exc:
        raise AssertionError(f"Invalid status value in {path}: {raw}") from exc


def _assert_status_zero(name: str) -> None:
    code = _status_code(name)
    assert code == 0, f"{name} exit code {code}; see {TEST_OUTPUT_DIR}/{name}.txt"


def _load_run_results(run_id: str) -> dict:
    return _read_json(RUNS_DIR / run_id / "results.json")


def _get_single_result(run_id: str) -> dict:
    data = _load_run_results(run_id)
    results = data.get("results", [])
    assert len(results) == 1, f"Expected 1 trial for run {run_id}, found {len(results)}"
    return results[0]


def _get_trial_output_dirs(run_id: str) -> list[Path]:
    data = _load_run_results(run_id)
    results = data.get("results", [])
    assert results, f"No trial results found for run {run_id}"
    output_dirs = []
    for entry in results:
        task_id = entry["task_id"]
        trial_name = entry["trial_name"]
        output_dirs.append(RUNS_DIR / run_id / task_id / trial_name / "test_output")
    return output_dirs


def _assert_nonempty(path: Path) -> None:
    assert _read_text(path).strip(), f"Empty file: {path}"


def _assert_skip_marker(path: Path) -> None:
    text = _read_text(path)
    assert SKIP_MARKER in text, f"Missing skip marker in {path}"


# Can tb run
def test_tb_help_exit_code_zero():
    _assert_status_zero("tb_help")
    text = _read_text(TEST_OUTPUT_DIR / "tb_help.txt")
    assert "command not found: tb" not in text

    

# Can Docker run?
def test_docker_version_exit_code_zero():
    _assert_status_zero("docker_version")

# # docker version
# def test_docker_version_no_command_not_found():
#     text = _read_text(TEST_OUTPUT_DIR / "docker_version.txt")
#     assert "command not found" not in text.lower()

# check docker_image_python_uv_pytest and docker_image_codex52 exist
def test_docker_image_python_uv_pytest_exists():
    _assert_status_zero("docker_image_python_uv_pytest")
    _assert_status_zero("docker_image_codex52")


# Did the modification of the codex's startup settings succeed?
def test_codex_setup_script_line_count():
    path = TB_ROOT / "terminal_bench/agents/installed_agents/codex/codex-setup.sh.j2"
    lines = _read_text(path).splitlines()
    assert len(lines) <= 3, f"Expected <=3 lines, got {len(lines)} in {path}"
    
    content = _read_text(path)
    assert 'echo "Codex has been installed, execute directly."' in content

# pytest_pytest_example test
def test_pytest_pytest_example_pass():
    # check run status
    # _assert_status_zero("tb_run_pytest_pytest_example")
    
    long_cli = _get_single_result("pytest_pytest_example")["long_cli"]
    assert long_cli["f2p_is_pass"] == 0
    assert long_cli["f2p_step_score"] == 0.0
    assert long_cli["p2p_is_pass"] == 1
    assert long_cli["p2p_step_score"] == 1.0
    # Is there a character to skip the agent?
    output_dir = _get_trial_output_dirs("pytest_pytest_example")[0]
    _assert_skip_marker(output_dir / "agent_output_turn1.txt")
    # Check if the output file is correct, whether it is not empty
    required = [
        "agent_instruction_turn1.txt",
        "agent_output_turn1.txt",
        "f2p_output_turn1.txt",
        "p2p_output_turn1.txt",
        "metrics_turn1.json",
    ]
    for name in required:
        _assert_nonempty(output_dir / name)




# pytest_pytest_example_finished test
def test_pytest_pytest_example_finished_pass():
    # First check the command execution status
    # _assert_status_zero("tb_run_pytest_pytest_example_finished")
    
    long_cli = _get_single_result("pytest_pytest_example_finished")["long_cli"]
    assert long_cli["f2p_is_pass"] == 1
    assert long_cli["f2p_step_score"] == 1.0
    assert long_cli["p2p_is_pass"] == 1
    assert long_cli["p2p_step_score"] == 1.0
    # Is there a character to skip the agent?
    output_dir = _get_trial_output_dirs("pytest_pytest_example_finished")[0]
    _assert_skip_marker(output_dir / "agent_output_turn1.txt")

# pytest_pytest_example_f2p test
def test_pytest_pytest_example_f2p_pass():
    # First check the execution status
    # _assert_status_zero("tb_run_pytest_pytest_example_f2p")
    long_cli = _get_single_result("pytest_pytest_example_f2p")["long_cli"]
    assert long_cli["f2p_is_pass"] == 0
    assert "p2p_is_pass" not in long_cli
    assert "p2p_step_score" not in long_cli
    # There is a field skipping the agent.
    output_dir = _get_trial_output_dirs("pytest_pytest_example_f2p")[0]
    _assert_skip_marker(output_dir / "agent_output_turn1.txt")
    # Is the file not empty?
    required = [
        "agent_instruction_turn1.txt",
        "agent_output_turn1.txt",
        "f2p_output_turn1.txt",
        "metrics_turn1.json",
    ]
    for name in required:
        _assert_nonempty(output_dir / name)
    assert not (output_dir / "p2p_output_turn1.txt").exists()


# pytest_pytest_example_1_3 test
def test_pytest_pytest_example_1_3_pass():
    # First check the execution status
    # _assert_status_zero("tb_run_pytest_pytest_example_1_3")
    # Is there a three-turn dialogue?
    entry = _get_single_result("pytest_pytest_example_1_3")
    turns = entry.get("long_cli_test_turns", [])
    assert len(turns) == 3, f"Expected 3 turns, found {len(turns)}"
    
    # Get the output folder
    output_dir = _get_trial_output_dirs("pytest_pytest_example_1_3")[0]
    # Ensure there is a field to skip agent execution.
    for turn in (1, 2, 3):
        _assert_skip_marker(output_dir / f"agent_output_turn{turn}.txt")
    # Each round of files exists
    for turn in (1, 2, 3):
        required = [
            f"agent_instruction_turn{turn}.txt",
            f"agent_output_turn{turn}.txt",
            f"f2p_output_turn{turn}.txt",
            f"p2p_output_turn{turn}.txt",
            f"metrics_turn{turn}.json",
        ]
        for name in required:
            _assert_nonempty(output_dir / name)
    # Each round of the conversation file is not empty.
    contents = []
    for turn in (1, 2, 3):
        path = output_dir / f"agent_instruction_turn{turn}.txt"
        text = _read_text(path).strip()
        assert text, f"Empty instruction file: {path}"
        contents.append(text)
    assert len(set(contents)) == 3, "Instruction outputs should differ across turns"
    



# pytest_pytest_example_3_1 test
def test_pytest_pytest_example_3_1_pass():
    # First check the execution status
    # _assert_status_zero("tb_run_pytest_pytest_example_3_1")
    data = _load_run_results("pytest_pytest_example_3_1")
    results = data.get("results", [])
    assert len(results) == 3, f"Expected 3 attempts, found {len(results)}"
    for output_dir in _get_trial_output_dirs("pytest_pytest_example_3_1"):
        _assert_skip_marker(output_dir / "agent_output_turn1.txt")

