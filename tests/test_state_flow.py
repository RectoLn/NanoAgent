import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from agent import ToolCallAgent
from session_manager import Session
from session_state import normalize_state


def _choice(*, finish_reason, content=None, tool_calls=None):
    return SimpleNamespace(
        finish_reason=finish_reason,
        message=SimpleNamespace(content=content, tool_calls=tool_calls or []),
    )


def _tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments, ensure_ascii=False)),
    )


class FakeLLM:
    def __init__(self):
        self.chat_calls = 0
        self.summary_calls = 0
        self.llm_messages = []

    def call(self, messages, tools=None, **kwargs):
        if tools is None:
            self.summary_calls += 1
            return {
                "choice": _choice(
                    finish_reason="stop",
                    content=json.dumps({
                        "progress_summary": "compressed summary: extracted PDF and read skill docs",
                        "file_knowledge": [],
                        "state_patch": {
                            "constraints": ["不要自己安装skill，使用已有的skill"],
                            "facts": ["PDF text extracted with PyMuPDF"],
                            "invalidated_assumptions": [],
                        },
                    }, ensure_ascii=False),
                ),
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            }

        self.chat_calls += 1
        self.llm_messages.append(messages)
        if self.chat_calls == 1:
            return {
                "choice": _choice(
                    finish_reason="tool_calls",
                    tool_calls=[
                        _tool_call(
                            "call_dup",
                            "todo_add",
                            {
                                "text": "读取guizang-ppt-skill模板和参考资料，了解布局结构",
                                "status": "pending",
                            },
                        )
                    ],
                ),
                "usage": {"prompt_tokens": 200, "completion_tokens": 20, "total_tokens": 220},
            }

        return {
            "choice": _choice(finish_reason="stop", content="done"),
            "usage": {"prompt_tokens": 120, "completion_tokens": 10, "total_tokens": 130},
        }


class StateFlowTest(unittest.TestCase):
    def test_compaction_preserves_todo_and_rejects_duplicate_add(self):
        session = Session("test_state_flow", system_prompt="system")
        session.tasks = [
            {"id": "1", "text": "提取林子越简历.pdf 完整内容", "status": "completed"},
            {"id": "2", "text": "读取 guizang-ppt-skill 模板和参考资料", "status": "completed"},
            {"id": "3", "text": "设计幻灯片结构并严格按照简历内容生成HTML", "status": "in_progress"},
            {"id": "4", "text": "读取guizang-ppt-skill模板和参考资料，了解布局结构", "status": "completed"},
            {"id": "5", "text": "提取并整理林子越简历完整内容", "status": "completed"},
        ]

        history = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "使用ppt skill为简历做幻灯片，不要自己安装skill"},
        ]
        for i in range(8):
            history.append({"role": "assistant", "content": f"step {i}"})
            history.append({
                "role": "tool",
                "tool_call_id": f"tool_{i}",
                "content": "large tool output\n" * 100,
            })

        llm = FakeLLM()
        agent = ToolCallAgent(llm, session_id=session.session_id, session=session)
        agent.l2_message_threshold = 12
        agent.l2_token_threshold = 1_000_000
        agent.l1_keep_recent = 1
        agent.l1_content_threshold = 80

        events = list(agent.run_iter("继续", history=history))

        self.assertTrue(any(event["type"] == "context_snapshot" for event in events))
        self.assertTrue(any(event["type"] == "compact" for event in events))
        observations = [event["content"] for event in events if event["type"] == "observation"]
        self.assertTrue(any("Todo already exists" in content for content in observations))

        todo_events = [event for event in events if event["type"] == "todo_update"]
        self.assertTrue(todo_events)
        self.assertEqual(
            [item["text"] for item in todo_events[-1]["items"]],
            [
                "提取林子越简历.pdf 完整内容",
                "读取 guizang-ppt-skill 模板和参考资料",
                "设计幻灯片结构并严格按照简历内容生成HTML",
            ],
        )

        snapshot = next(event["messages"] for event in events if event["type"] == "context_snapshot")
        snapshot_text = "\n".join(str(message.get("content", "")) for message in snapshot)
        self.assertIn("compressed summary", snapshot_text)
        self.assertIn("Current Todo list:", snapshot_text)
        self.assertEqual(llm.summary_calls, 1)
        self.assertGreaterEqual(llm.chat_calls, 2)

    def test_state_normalization_removes_constraint_invalidated_overlap(self):
        state = {
            "constraints": [
                {"text": "不要自己安装skill，使用已有的skill", "source": "user"},
            ],
            "invalidated_assumptions": [
                {"text": "不要自己安装skill，使用已有的skill", "source": "user"},
                {"text": "假设需要安装ppt skill被纠正", "source": "llm_inferred"},
            ],
        }

        normalized = normalize_state(state)
        invalidated_texts = [item["text"] for item in normalized["invalidated_assumptions"]]
        self.assertNotIn("不要自己安装skill，使用已有的skill", invalidated_texts)
        self.assertIn("假设需要安装ppt skill被纠正", invalidated_texts)


if __name__ == "__main__":
    unittest.main()
