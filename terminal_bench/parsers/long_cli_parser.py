from terminal_bench.parsers.base_parser import BaseParser, UnitTestStatus


class LongCliParser(BaseParser):
    """A no-op parser for tasks that report metrics via /app/metrics.json.

    - Does not attempt to parse terminal output.
    - Returns a trivial passed result to avoid parse errors.
    - Actual metrics are collected separately by the harness into results.long_cli.
    """

    def parse(self, content: str) -> dict[str, UnitTestStatus]:
        # Always report a single passed test to mark the task as resolved
        # while the real metrics live in results.long_cli.
        return {"long_cli": UnitTestStatus.PASSED}

