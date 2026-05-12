import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")
    openai_stub.OpenAI = object
    sys.modules["openai"] = openai_stub

from agent import ToolCallAgent
from app.llm.types import LLMResponse, ToolCall, Usage
from session_manager import Session


class BadToolCallLLM:
    def call(self, messages, tools=None, **kwargs):
        return LLMResponse(
            content=None,
            finish_reason="tool_calls",
            tool_calls=[
                ToolCall(
                    id="bad_call",
                    name="edit",
                    arguments='{"new_str": "unterminated </tool_call>',
                )
            ],
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )


class ToolCallJsonGuardTest(unittest.TestCase):
    def test_invalid_tool_call_arguments_are_not_persisted_as_tool_calls(self):
        agent = ToolCallAgent(BadToolCallLLM())

        events = list(agent.run_iter("continue", history=[{"role": "user", "content": "go"}]))

        self.assertTrue(any(event.get("type") == "error" for event in events))
        self.assertEqual(events[-1].get("type"), "done")
        assistant_messages = [
            msg for msg in agent.messages if msg.get("role") == "assistant"
        ]
        self.assertEqual(len(assistant_messages), 1)
        self.assertNotIn("tool_calls", assistant_messages[0])
        self.assertIn("格式错误", assistant_messages[0].get("content", ""))
        self.assertFalse(any(msg.get("role") == "tool" for msg in agent.messages))

    def test_session_llm_history_filters_existing_invalid_tool_call_groups(self):
        session = Session("bad-history", system_prompt="system")
        session.messages = [
            {"role": "user", "content": "start"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "bad_call",
                        "type": "function",
                        "function": {
                            "name": "edit",
                            "arguments": '{"new_str": "unterminated </tool_call>',
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "bad_call", "content": "parse failed"},
            {"role": "user", "content": "continue"},
        ]

        llm_messages = session.get_messages_for_llm()

        self.assertEqual([msg["role"] for msg in llm_messages], ["system", "user", "user"])
        self.assertFalse(any(msg.get("tool_calls") for msg in llm_messages))


if __name__ == "__main__":
    unittest.main()
