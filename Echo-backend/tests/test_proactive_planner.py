import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.agent.domain.entities import AgentModelResponse, ProactiveAction
from features.agent.domain.services import AgentModelTimeoutError, ProactivePlannerError
from features.agent.infrastructure.proactive_planner import (
    ProviderProactiveDecisionPlanner,
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
    async def test_valid_decision_uses_only_available_fact_ids(self):
        model = SequenceModel(
            [
                AgentModelResponse(
                    text=(
                        '{"action":"send","topic":"casual_check_in",'
                        '"tone":"warm","safe_fact_ids":'
                        '["conversation_gap","last_user_message"],"reason":"natural"}'
                    )
                )
            ]
        )
        planner = ProviderProactiveDecisionPlanner(model)

        decision = await planner.decide(
            [{"role": "system", "content": "internal context"}],
            ("conversation_gap",),
        )

        self.assertEqual(ProactiveAction.SEND, decision.action)
        self.assertEqual(("conversation_gap",), decision.safe_fact_ids)
        self.assertTrue(model.calls[0]["structured_output"])
        self.assertEqual((), model.calls[0]["tools"])
        self.assertEqual("none", model.calls[0]["tool_choice"])
        prompt = "\n".join(str(item.get("content") or "") for item in model.calls[0]["messages"])
        self.assertIn('"action":"send"', prompt)
        self.assertIn('"safe_fact_ids":["conversation_gap"]', prompt)
        self.assertIn("Do not wrap the object in Markdown fences", prompt)

    async def test_malformed_spontaneous_decision_retries_then_reports_technical_failure(self):
        model = SequenceModel(
            [
                AgentModelResponse(text='{"action"', provider_request_id="request-1"),
                AgentModelResponse(text="not-json", provider_request_id="request-2"),
            ]
        )
        planner = ProviderProactiveDecisionPlanner(model)

        with self.assertRaises(ProactivePlannerError) as raised:
            await planner.decide([], ("conversation_gap",))

        self.assertEqual("planner_output_invalid", raised.exception.code)
        self.assertEqual(2, len(model.calls))
        retry_prompt = str(model.calls[1]["messages"][-1]["content"])
        self.assertIn("previous planner response", retry_prompt.lower())

    async def test_empty_spontaneous_decision_can_recover_on_retry(self):
        model = SequenceModel(
            [
                AgentModelResponse(text="", finish_reason="stop"),
                AgentModelResponse(
                    text=(
                        '{"action":"send","topic":"share_presence",'
                        '"tone":"gentle","safe_fact_ids":["conversation_gap"],'
                        '"reason":"natural"}'
                    ),
                    provider_request_id="request-recovered",
                ),
            ]
        )
        planner = ProviderProactiveDecisionPlanner(model)

        decision = await planner.decide([], ("conversation_gap",))

        self.assertEqual(ProactiveAction.SEND, decision.action)
        self.assertEqual(("conversation_gap",), decision.safe_fact_ids)
        self.assertEqual(2, len(model.calls))

    async def test_empty_spontaneous_decision_has_specific_error_code(self):
        model = SequenceModel([AgentModelResponse(text="")])
        planner = ProviderProactiveDecisionPlanner(model, format_retries=0)

        with self.assertRaises(ProactivePlannerError) as raised:
            await planner.decide([], ("conversation_gap",))

        self.assertEqual("planner_output_empty", raised.exception.code)

    async def test_missing_required_fields_are_rejected(self):
        model = SequenceModel([AgentModelResponse(text='{"action":"skip"}')])
        planner = ProviderProactiveDecisionPlanner(model, format_retries=0)

        with self.assertRaises(ProactivePlannerError) as raised:
            await planner.decide([], ("conversation_gap",))

        self.assertEqual("planner_output_invalid", raised.exception.code)

    async def test_timeout_is_not_reported_as_business_skip(self):
        model = SequenceModel([AgentModelTimeoutError("timeout")])
        planner = ProviderProactiveDecisionPlanner(model)

        with self.assertRaises(ProactivePlannerError) as raised:
            await planner.decide([], ("conversation_gap",))

        self.assertEqual("planner_timeout", raised.exception.code)
        self.assertEqual(1, len(model.calls))

    async def test_malformed_explicit_schedule_uses_minimum_safe_send_plan(self):
        model = SequenceModel(
            [
                AgentModelResponse(text="not-json"),
                AgentModelResponse(text='{"action"'),
            ]
        )
        planner = ProviderProactiveDecisionPlanner(model)

        decision = await planner.decide(
            [],
            ("task_intent", "current_day_period", "last_user_message"),
            force_send=True,
        )

        self.assertEqual(ProactiveAction.SEND, decision.action)
        self.assertEqual("scheduled_reminder", decision.topic)
        self.assertEqual(("task_intent", "current_day_period"), decision.safe_fact_ids)
        self.assertEqual("planner_output_invalid", decision.reason)
        self.assertEqual(2, len(model.calls))


if __name__ == "__main__":
    unittest.main()
