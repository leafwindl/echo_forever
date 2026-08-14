import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.agent.domain.entities import AgentModelResponse, ProactiveAction
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
        return self.responses.pop(0)


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

    async def test_malformed_spontaneous_decision_fails_closed_to_skip(self):
        model = SequenceModel([AgentModelResponse(text='{"action"')])
        planner = ProviderProactiveDecisionPlanner(model)

        decision = await planner.decide([], ("conversation_gap",))

        self.assertEqual(ProactiveAction.SKIP, decision.action)
        self.assertEqual((), decision.safe_fact_ids)

    async def test_malformed_explicit_schedule_uses_minimum_safe_send_plan(self):
        model = SequenceModel([AgentModelResponse(text="not-json")])
        planner = ProviderProactiveDecisionPlanner(model)

        decision = await planner.decide(
            [],
            ("task_intent", "current_day_period", "last_user_message"),
            force_send=True,
        )

        self.assertEqual(ProactiveAction.SEND, decision.action)
        self.assertEqual("scheduled_reminder", decision.topic)
        self.assertEqual(("task_intent", "current_day_period"), decision.safe_fact_ids)


if __name__ == "__main__":
    unittest.main()
