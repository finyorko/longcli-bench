import os
import shlex
from pathlib import Path

from terminal_bench.agents.installed_agents.abstract_installed_agent import (
    AbstractInstalledAgent,
)
from terminal_bench.terminal.models import TerminalCommand


class AgentMAgent(AbstractInstalledAgent):
    """AgentM agent adapter for terminal-bench / longcli-bench.

    Installs AgentM into the task container via uv and runs it with the
    local scenario (bash + file tools).

    Environment variables (set on the host, forwarded into the container):
      LLM_BASE_URL   — OpenAI-compatible endpoint (e.g. http://host:8088/v1)
      LLM_API_KEY    — API key for the endpoint

    Usage:
        LLM_BASE_URL="http://localhost:8088/v1" LLM_API_KEY="..." \
        tb run --agent-import-path \
            terminal_bench.agents.installed_agents.agentm.agentm_agent:AgentMAgent \
            --model doubao-seed-2-0-pro-260215 \
            --task-id <task_id> \
            --dataset-path tasks_long_cli
    """

    def __init__(self, model_name: str | None = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._model_name = model_name

    @staticmethod
    def name() -> str:
        return "agentm"

    @property
    def _env(self) -> dict[str, str]:
        env: dict[str, str] = {
            "AGENTM_PROVIDER": "openai",
        }
        if self._model_name:
            env["AGENTM_MODEL"] = self._model_name

        base_url = os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
        if base_url:
            env["AGENTM_BASE_URL"] = base_url
            env["OPENAI_BASE_URL"] = base_url

        api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if api_key:
            env["AGENTM_API_KEY"] = api_key
            env["OPENAI_API_KEY"] = api_key

        return env

    @property
    def _install_agent_script_path(self) -> Path:
        return self._get_templated_script_path("agentm-setup.sh.j2")

    def _run_agent_commands(self, instruction: str) -> list[TerminalCommand]:
        escaped = shlex.quote(instruction)
        return [
            TerminalCommand(
                command=f"agentm --scenario local -p {escaped}",
                min_timeout_sec=0.0,
                max_timeout_sec=float("inf"),
                block=True,
                append_enter=True,
            ),
        ]
