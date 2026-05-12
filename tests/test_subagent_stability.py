import json
import os
import queue
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

# The unit tests below mock every LLM call. Provide a tiny import stub so the
# production client module can be imported in environments without openai.
if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")
    openai_stub.OpenAI = object
    sys.modules["openai"] = openai_stub

import agent as agent_module
from agent import ToolCallAgent
from app.llm import provider_config
from app.llm.types import LLMResponse, ToolCall, Usage
from tools import subagent as subagent_module


RUNS = int(os.getenv("SUBAGENT_STABILITY_RUNS", "25"))


def _tool_call(call_id, name, arguments):
    return ToolCall(
        id=call_id,
        name=name,
        arguments=json.dumps(arguments, ensure_ascii=False),
    )


class FakeSubagentLLM:
    last_init = None

    def __init__(self, purpose="chat", override=None):
        type(self).last_init = {"purpose": purpose, "override": override}

    def call(self, messages, tools=None, **kwargs):
        return LLMResponse(
            content=(
                "## 结论\n子任务成功完成。\n\n"
                "## 产出物\n- /app/workspace/wiki/concepts/test-subagent.md\n\n"
                "## 关键发现\n队列事件完整。\n\n"
                "## 未完成项\n无。"
            ),
            finish_reason="stop",
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )


class FakeChildAgent:
    def __init__(self, *args, **kwargs):
        self.messages = [
            {"role": "user", "content": "子任务：稳定性测试"},
            {"role": "tool", "tool_call_id": "child_1", "content": "read ok"},
        ]

    def run_iter(self, question):
        yield {
            "type": "tool_call",
            "call_id": "child_1",
            "name": "read",
            "input_preview": '{"path": "wiki/test.md"}',
        }
        yield {
            "type": "observation",
            "call_id": "child_1",
            "content": "read ok",
        }
        yield {
            "type": "tool_call",
            "call_id": "child_2",
            "name": "write_file",
            "input_preview": '{"path": "wiki/test.md", "content": "..."}',
        }
        yield {
            "type": "observation",
            "call_id": "child_2",
            "content": "write ok " + ("x" * 180),
        }
        yield {"type": "final", "content": "done"}
        yield {"type": "done"}


class ParentRunSubagentLLM:
    provider = "kilo"
    model = "kilo-auto/free"

    def __init__(self):
        self.calls = 0

    def call(self, messages, tools=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content=None,
                finish_reason="tool_calls",
                tool_calls=[
                    _tool_call(
                        "parent_subagent",
                        "run_subagent",
                        {
                            "task": "执行稳定性测试子任务",
                            "context": "测试上下文",
                        },
                    )
                ],
                usage=Usage(prompt_tokens=20, completion_tokens=5, total_tokens=25),
            )
        return LLMResponse(
            content="parent done",
            finish_reason="stop",
            usage=Usage(prompt_tokens=15, completion_tokens=5, total_tokens=20),
        )


class SubagentStabilityTest(unittest.TestCase):
    def test_run_subagent_queue_events_success_rate(self):
        old_llm = subagent_module.LLMClient
        old_agent = subagent_module.ToolCallAgent
        successes = 0

        try:
            subagent_module.LLMClient = FakeSubagentLLM
            subagent_module.ToolCallAgent = FakeChildAgent

            for idx in range(RUNS):
                call_id = f"parent_{idx}"
                events = queue.Queue()
                summary = subagent_module.run_subagent(
                    "稳定性测试",
                    context="检查队列事件",
                    event_queue=events,
                    call_id=call_id,
                )
                drained = []
                while not events.empty():
                    drained.append(events.get_nowait())

                step_events = [ev for ev in drained if not ev.get("done")]
                done_events = [ev for ev in drained if ev.get("done")]
                ok = (
                    "## 结论" in summary
                    and len(step_events) == 2
                    and len(done_events) == 1
                    and done_events[-1]["summary"] == summary
                    and all(ev["call_id"] == call_id for ev in drained)
                    and [ev["step"] for ev in step_events] == [1, 2]
                    and [ev["tool"] for ev in step_events] == ["read", "write_file"]
                    and len(step_events[-1]["observation_preview"]) <= 121
                )
                successes += int(ok)
        finally:
            subagent_module.LLMClient = old_llm
            subagent_module.ToolCallAgent = old_agent

        self.assertEqual(successes, RUNS)

    def test_parent_agent_yields_subagent_sse_events_success_rate(self):
        old_run_subagent = subagent_module.run_subagent
        successes = 0

        seen_parent_config = []

        def fake_run_subagent(
            task,
            context="",
            event_queue=None,
            call_id="",
            parent_provider="",
            parent_model_id="",
        ):
            seen_parent_config.append((parent_provider, parent_model_id))
            event_queue.put({
                "type": "subagent_step",
                "call_id": call_id,
                "step": 1,
                "tool": "read",
                "input_preview": '{"path": "wiki/test.md"}',
                "observation_preview": "read ok",
                "done": False,
            })
            summary = (
                "## 结论\n父 Agent 成功转发 subagent 事件。\n\n"
                "## 产出物\n- /app/workspace/wiki/concepts/test-subagent.md\n\n"
                "## 关键发现\nSSE 事件顺序正确。\n\n"
                "## 未完成项\n无。"
            )
            event_queue.put({
                "type": "subagent_step",
                "call_id": call_id,
                "done": True,
                "summary": summary,
            })
            return summary

        try:
            subagent_module.run_subagent = fake_run_subagent
            for _ in range(RUNS):
                agent = ToolCallAgent(ParentRunSubagentLLM())
                events = list(agent.run_iter("测试 subagent SSE 转发"))

                subagent_steps = [
                    ev for ev in events
                    if ev.get("type") == "subagent_step" and not ev.get("done")
                ]
                observations = [
                    ev for ev in events
                    if ev.get("type") == "observation"
                    and ev.get("call_id") == "parent_subagent"
                ]
                ok = (
                    any(ev.get("type") == "tool_call" and ev.get("name") == "run_subagent" for ev in events)
                    and len(subagent_steps) == 1
                    and subagent_steps[0]["tool"] == "read"
                    and len(observations) == 1
                    and "## 结论" in observations[0]["content"]
                    and any(ev.get("type") == "final" and ev.get("content") == "parent done" for ev in events)
                    and events[-1].get("type") == "done"
                )
                successes += int(ok)
        finally:
            subagent_module.run_subagent = old_run_subagent

        self.assertEqual(successes, RUNS)
        self.assertEqual(seen_parent_config, [("kilo", "kilo-auto/free")] * RUNS)

    def test_subagent_llm_config_prefers_subagent_env_then_parent_override(self):
        keys = [
            "SUBAGENT_LLM_PROVIDER",
            "SUBAGENT_LLM_API_KEY",
            "SUBAGENT_LLM_BASE_URL",
            "SUBAGENT_LLM_MODEL_ID",
            "LLM_BASE_URL",
            "LLM_MODEL_ID",
            "LLM_API_KEY",
        ]
        old_env = {key: os.environ.get(key) for key in keys}

        try:
            for key in keys:
                os.environ.pop(key, None)

            inherited = provider_config.resolve(
                "subagent",
                {"provider": "kilo", "model_id": "parent-model"},
            )
            self.assertEqual(inherited.provider, "kilo")
            self.assertEqual(inherited.model, "parent-model")

            os.environ["SUBAGENT_LLM_PROVIDER"] = "deepseek"
            os.environ["SUBAGENT_LLM_BASE_URL"] = "https://subagent.example/v1"
            os.environ["SUBAGENT_LLM_MODEL_ID"] = "subagent-model"
            os.environ["SUBAGENT_LLM_API_KEY"] = "subagent-key"
            explicit = provider_config.resolve(
                "subagent",
                {"provider": "kilo", "model_id": "parent-model"},
            )
            self.assertEqual(explicit.provider, "deepseek")
            self.assertEqual(explicit.base_url, "https://subagent.example/v1")
            self.assertEqual(explicit.model, "subagent-model")
            self.assertEqual(explicit.api_key, "subagent-key")

            os.environ.pop("SUBAGENT_LLM_MODEL_ID")
            provider_only = provider_config.resolve(
                "subagent",
                {"provider": "kilo", "model_id": "parent-model"},
            )
            self.assertEqual(provider_only.provider, "deepseek")
            self.assertEqual(provider_only.model, "deepseek-chat")
        finally:
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
