from __future__ import annotations

import json
import uuid

from db.postgres_connection import transaction


class PostgresAgentRunRepository:
    def start(self, user_id: str, objective: str, trigger_type: str, max_steps: int) -> str:
        run_id = f"run_{uuid.uuid4().hex}"
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO agent_runs (
                    run_id, user_id, trigger_type, status, objective, max_steps, started_at
                ) VALUES (%s, %s, %s, 'running', %s, %s, NOW())
                """,
                (run_id, user_id, trigger_type, objective[:500], max_steps),
            )
        return run_id

    def record_tool_call(
        self,
        run_id: str,
        tool_name: str,
        arguments: dict,
        output: dict,
        error_code: str | None = None,
        status: str | None = None,
        tool_call_id: str | None = None,
    ) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO agent_tool_calls (
                    tool_call_id, run_id, tool_name, status, input_summary,
                    output_summary, error_code, started_at, finished_at
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, NOW(), NOW())
                """,
                (
                    tool_call_id or f"tool_{uuid.uuid4().hex}",
                    run_id,
                    tool_name,
                    status or ("failed" if error_code else "completed"),
                    json.dumps(arguments, ensure_ascii=False),
                    json.dumps(output, ensure_ascii=False),
                    error_code,
                ),
            )

    def finish(self, run_id: str, step_count: int, error_code: str | None = None) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE agent_runs SET status = %s, step_count = %s,
                    error_code = %s, finished_at = NOW()
                WHERE run_id = %s
                """,
                ("failed" if error_code else "completed", step_count, error_code, run_id),
            )
