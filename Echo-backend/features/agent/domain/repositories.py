from typing import Protocol


class AgentRunRepository(Protocol):
    def start(self, user_id: str, objective: str, trigger_type: str, max_steps: int) -> str: ...

    def record_tool_call(
        self,
        run_id: str,
        tool_name: str,
        arguments: dict,
        output: dict,
        error_code: str | None = None,
        status: str | None = None,
        tool_call_id: str | None = None,
    ) -> None: ...

    def finish(self, run_id: str, step_count: int, error_code: str | None = None) -> None: ...
