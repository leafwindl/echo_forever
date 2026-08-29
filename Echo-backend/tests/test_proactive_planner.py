import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.agent.domain.entities import (
    AgentModelResponse,
    AgentToolCall,
    ProactiveAction,
)
from features.agent.domain.services import AgentModelTimeoutError, ProactivePlannerError
from features.agent.infrastructure.proactive_planner import (
    ProviderProactiveDecisionPlanner,
)


def tool_response(arguments, request_id=""):
    return AgentModelResponse(
        tool_calls=(
            AgentToolCall(
                call_id="call-1",
                tool_name="decide_proactive_message",
                arguments=arguments,
            ),
        ),
        finish_reason="tool_calls",
        provider_request_id=request_id,
    )


class SequenceModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def complete(
        self,
        messages,
        tools,
        *,
        structured_output=False,
        tool_choice="auto",
    ):
        self.calls.append(
            {
                "messages": list(messages),
                "tools": tuple(tools),
                "structured_output": structured_output,
                "tool_choice": tool_choice,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class ProactivePlannerTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_decision_uses_compact_facts_and_required_tool(self):
        model = SequenceModel(
            [
                tool_response(
                    {
                        "action": "send",
                        "topic": "follow_up_past_topic",
                        "tone": "encouraging",
                        "safe_fact_ids": ["conversation_gap", "last_user_message"],
                        "reason": "natural",
                    }
                )
            ]
        )
        planner = ProviderProactiveDecisionPlanner(model)

        decision = await planner.decide(
            {
                "current_local_time": "2026-08-29T21:00:00+08:00",
                "current_day_period": "晚上",
                "conversation_gap": {"gap_seconds": 7200, "state": "long_absence"},
                "last_user_message": "今天任务有点多",
                "ignored_attachment": "should not be sent",
            }
        )

        self.assertEqual(ProactiveAction.SEND, decision.action)
        self.assertEqual(("conversation_gap", "last_user_message"), decision.safe_fact_ids)
        self.assertFalse(model.calls[0]["structured_output"])
        self.assertEqual(
            "decide_proactive_message",
            model.calls[0]["tool_choice"]["function"]["name"],
        )
        self.assertEqual(1, len(model.calls[0]["tools"]))
        prompt = "\n".join(str(item.get("content") or "") for item in model.calls[0]["messages"])
        self.assertIn("Backend proactive facts", prompt)
        self.assertIn("今天任务有点多", prompt)
        self.assertNotIn("ignored_attachment", prompt)

    async def test_invalid_tool_arguments_retry_then_report_technical_failure(self):
        model = SequenceModel(
            [
                tool_response({"action": "skip"}, request_id="request-1"),
                AgentModelResponse(
                    text="not-a-tool-call",
                    finish_reason="stop",
                    provider_request_id="request-2",
                ),
            ]
        )
        planner = ProviderProactiveDecisionPlanner(model)

        with self.assertRaises(ProactivePlannerError) as raised:
            await planner.decide({"conversation_gap": {"state": "returned"}})

        self.assertEqual("planner_output_invalid", raised.exception.code)
        self.assertEqual(2, len(model.calls))
        retry_prompt = str(model.calls[1]["messages"][-1]["content"])
        self.assertIn("decide_proactive_message", retry_prompt)

    async def test_prose_or_json_content_without_tool_is_rejected(self):
        model = SequenceModel(
            [AgentModelResponse(text='{"action":"skip"}', finish_reason="stop")]
        )
        planner = ProviderProactiveDecisionPlanner(model, format_retries=0)

        with self.assertRaises(ProactivePlannerError) as raised:
            await planner.decide({"conversation_gap": {"state": "returned"}})

        self.assertEqual("planner_output_invalid", raised.exception.code)

    async def test_timeout_is_not_reported_as_business_skip(self):
        model = SequenceModel([AgentModelTimeoutError("timeout")])
        planner = ProviderProactiveDecisionPlanner(model)

        with self.assertRaises(ProactivePlannerError) as raised:
            await planner.decide({"conversation_gap": {"state": "returned"}})

        self.assertEqual("planner_timeout", raised.exception.code)
        self.assertEqual(1, len(model.calls))

    async def test_malformed_explicit_schedule_uses_minimum_safe_send_plan(self):
        model = SequenceModel(
            [
                AgentModelResponse(text="not-a-tool-call"),
                AgentModelResponse(text="still-not-a-tool-call"),
            ]
        )
        planner = ProviderProactiveDecisionPlanner(model)

        decision = await planner.decide(
            {
                "task_intent": "提醒用户确认组会材料",
                "current_day_period": "晚上",
                "last_user_message": "准备明天的组会",
            },
            force_send=True,
        )

        self.assertEqual(ProactiveAction.SEND, decision.action)
        self.assertEqual("scheduled_reminder", decision.topic)
        self.assertEqual(("task_intent", "current_day_period"), decision.safe_fact_ids)
        self.assertEqual("planner_output_invalid", decision.reason)
        self.assertEqual(2, len(model.calls))


if __name__ == "__main__":
    unittest.main()
