"""
ToolCallAgent：基于 OpenAI Tool Call 协议的 Agent 主循环。

消息结构（标准 messages 列表）：
  user       → 用户问题
  assistant  → 模型回复（含 tool_calls 或最终 content）
  tool       → 工具执行结果（role=tool, tool_call_id=xxx）

事件流（供 server.py SSE 使用）：
  question         用户问题
  tool_call        模型发起工具调用  {name, input_preview}
  observation      工具执行结果
  todo_update      todo 列表快照
  answer_chunk     最终答案流式 token
  final            最终答案完整文本
  compact          上下文压缩事件（Layer 2/3 触发）
  error            错误
  done             结束
"""

import json
import sys
import yaml
from pathlib import Path
from typing import Callable, Generator, Dict, Any, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from compression import CompressionMixin
from app.llm.client import LLMClient
from app.llm.types import Usage
from app.prompt_loader import load_prompt
from registry import TOOL_EXECUTORS, TOOLS_SCHEMA, execute_tool_call, set_thread_local_todo
from session_manager import SESSION_MGR
from session_state import (
    extract_state_from_message,
    format_authoritative_state,
)
from subagent_runner import run_subagent_with_events
from todo_manager import TodoManager


def _load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class ToolCallAgent(CompressionMixin):
    """Tool Call 模式 Agent"""

    def __init__(
        self,
        llm: LLMClient,
        session_id: Optional[str] = None,
        session = None,
        todo: TodoManager = None,
        tools_override: dict = None,
        system_prompt: str = None,
    ):
        self.llm = llm
        self.llm_provider = getattr(llm, "provider", "") or ""
        self.llm_model_id = getattr(llm, "model", "") or getattr(llm, "_model", "") or ""
        self.config = _load_config()
        self.session_id = session_id
        self.session = session  # Session 对象引用，用于 compression_history
        self.tools = tools_override if tools_override is not None else TOOL_EXECUTORS
        self.tools_schema = [
            schema for schema in TOOLS_SCHEMA
            if (schema.get("function") or {}).get("name") in self.tools
        ]
        self.messages: List[Dict[str, Any]] = []

        agent_cfg = self.config.get("agent", {})
        self.max_steps = agent_cfg.get("max_steps", 30)
        self.temperature = agent_cfg.get("temperature", 0.1)
        self.max_tokens = agent_cfg.get("max_tokens", 16384)

        # 最近一次精准的 prompt_tokens（来自 LLM API 返回的 usage）
        self.last_precise_prompt_tokens: Optional[int] = None

        # 压缩配置（三层策略 - 仅暴露可调参数到 YAML）
        comp_cfg = self.config.get("compression", {})
        self.comp_enabled = comp_cfg.get("enabled", True)

        # Layer 1: micro_compact
        l1_cfg = comp_cfg.get("layer1", {})
        self.l1_keep_recent = l1_cfg.get("keep_recent_tool_messages", 3)
        self.l1_content_threshold = l1_cfg.get("content_threshold", 100)
        # 占位符硬编码（无需配置）
        self.l1_placeholder_template = "[Previous: {tool_call_id} result truncated]"

        # Layer 2: auto_compact
        l2_cfg = comp_cfg.get("layer2", {})
        self.l2_token_threshold = l2_cfg.get("token_threshold", 40000)
        self.l2_message_threshold = l2_cfg.get("message_threshold", 30)
        l2_summary = l2_cfg.get("summary", {})
        self.l2_summary_temperature = l2_summary.get("temperature", 0.1)
        self.l2_summary_max_tokens = l2_summary.get("max_tokens", 1000)
        self.l2_summary_retry_max_tokens = l2_summary.get(
            "retry_max_tokens",
            max(self.l2_summary_max_tokens * 3, 1500),
        )
        self.l2_summary_max_chars = l2_summary.get("max_chars", 800)
        self.l2_summary_max_input_chars = l2_summary.get("max_input_chars", 24000)
        self.l2_prompt_file = l2_summary.get("prompt", "compression_summary.md")
        self.l2_prompt_template = load_prompt(self.l2_prompt_file)
        self.l2_fallback_prompt_file = l2_summary.get(
            "fallback_prompt",
            "compression_summary_fallback.md",
        )
        self.compaction_hint_file = l2_summary.get(
            "subagent_hint_prompt",
            "compression_subagent_hint.md",
        )
        self.compaction_hint = load_prompt(self.compaction_hint_file)
        # 总是保存 transcript（无需配置）
        self.l2_save_transcript = True

        # Layer 3: compact 工具（描述硬编码）
        self.l3_tool_description = "当你感到上下文过长影响推理时，主动调用此工具压缩上下文。"

        # 摘要消息格式（硬编码）
        self.summary_role = "user"
        self.summary_prefix = "[上下文摘要]\n\n"

        prompts_cfg = self.config.get("prompts", {})
        prompt_file = prompts_cfg.get("system", "prompts/system.md")
        self.system_prompt = system_prompt if system_prompt is not None else load_prompt(prompt_file)

        # 每个 Agent 持有独立的 TodoManager 实例（而非全局单例）
        self.todo = todo or TodoManager()
        if self.session and getattr(self.session, "tasks", None):
            self.todo.items = self.todo.dedupe_items([dict(item) for item in self.session.tasks])

    def _execute_tool_call(self, tool_name: str, arguments_json: str) -> str:
        return execute_tool_call(tool_name, arguments_json, executors=self.tools)

    def _invalid_tool_call_error(self, tool_calls) -> Optional[str]:
        for tc in tool_calls or []:
            args_json = tc.arguments or "{}"
            try:
                json.loads(args_json) if args_json.strip() else {}
            except json.JSONDecodeError as exc:
                preview = args_json[:160].replace("\n", "\\n")
                return (
                    f"Invalid JSON in tool call arguments for `{tc.name}` "
                    f"({tc.id}): {exc}. Preview: {preview}"
                )
        return None

    def _new_summary_llm(self):
        return LLMClient(purpose="summary")

    # ── LLM 调用前消息准备 ──────────────────────────────────────────────────

    def _is_authoritative_state_message(self, msg: Dict[str, Any]) -> bool:
        content = msg.get("content") or ""
        return isinstance(content, str) and content.startswith("[Authoritative Session State]")

    def _inject_authoritative_state(self, messages: List[Dict]) -> List[Dict]:
        """Return an LLM-ready message copy with durable session state injected."""
        cleaned = [
            dict(msg) for msg in messages
            if not self._is_authoritative_state_message(msg)
        ]
        if not self.session:
            return cleaned

        state_text = format_authoritative_state(getattr(self.session, "state", None))
        if not state_text:
            return cleaned

        state_msg = {"role": "user", "content": state_text}

        insert_at = 0
        while insert_at < len(cleaned) and cleaned[insert_at].get("role") == "system":
            insert_at += 1
        if insert_at < len(cleaned) and cleaned[insert_at].get("role") == "user":
            insert_at += 1

        return cleaned[:insert_at] + [state_msg] + cleaned[insert_at:]

    def run_iter(
        self,
        question: str,
        history: Optional[List[Dict]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        以生成器方式执行 Tool Call 主循环，逐步产出事件字典。

        参数：
          question: 当前用户输入
          history:  已有的多轮消息历史（OpenAI格式，含 system），由 Session 提供。
                    若为 None，则新建单轮对话（含 system+user）。

        事件类型：
          {"type": "question",     "content": str}
          {"type": "tool_call",    "name": str, "input_preview": str, "call_id": str}
          {"type": "observation",  "content": str, "call_id": str}
          {"type": "todo_update",  "items": list}
          {"type": "answer_chunk", "content": str}   # 流式 token
          {"type": "final",        "content": str}   # 完整最终答案
          {"type": "message_delta", "message": dict} # 已产生并应立即持久化的单条消息
          {"type": "context_snapshot", "messages": list} # 压缩后的可恢复上下文快照
          {"type": "new_messages", "messages": list} # 本轮新增消息（供 session 追加）
          {"type": "error",        "content": str}
          {"type": "done"}
        """
        def cancel_requested() -> bool:
            return bool(should_cancel and should_cancel())

        def cancel_events():
            yield {"type": "cancelled", "content": "任务已停止"}
            yield {"type": "done"}

        yield {"type": "question", "content": question}

        # 如果有 history（含 system），直接使用并追加本轮 user 消息
        # 否则构建新对话
        if history is not None:
            messages: List[Dict] = list(history)
            messages.append({"role": "user", "content": question})
        else:
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": question},
            ]
        self.messages = messages

        # 记录本轮新增消息（不含历史），供 session 保存
        new_messages: List[Dict] = [{"role": "user", "content": question}]
        if self.session:
            self.session.update_state(extract_state_from_message(new_messages[0]))
        yield {"type": "message_delta", "message": new_messages[0]}
        round_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        for step in range(1, self.max_steps + 1):
            if cancel_requested():
                yield from cancel_events()
                return

            # ── Layer 1：micro_compact 每次 LLM 调用前静默执行 ─────────────
            messages = self.micro_compact(messages)
            self.messages = messages

            # ── Layer 2：token 或消息数超阈值时自动触发 auto_compact ─────────
            if self.comp_enabled:
                # 排除 system 消息统计
                non_system = [m for m in messages if m.get("role") != "system"]
                msg_count = len(non_system)

                # 优先使用精准 prompt_tokens（如果可用），否则估算
                estimated_tokens = self.estimate_tokens(non_system)
                if self.last_precise_prompt_tokens is not None:
                    token_count = max(self.last_precise_prompt_tokens, estimated_tokens)
                else:
                    token_count = estimated_tokens

                if token_count > self.l2_token_threshold or msg_count > self.l2_message_threshold:
                    messages = self.auto_compact(messages)
                    self.messages = messages
                    # 重置精准计数（压缩后历史已变，旧值不再适用）
                    self.last_precise_prompt_tokens = None
                    yield {"type": "context_snapshot", "messages": messages}
                    yield {"type": "compact", "content": "上下文已自动压缩"}

            # ── 注入当前 Agent 的 TodoManager 和 Session 到线程局部，供工具函数访问 ──
            set_thread_local_todo(self.todo, self.session)

            # ── 请求模型（非流式，获取 tool_calls 或 stop）──────────────
            if cancel_requested():
                yield from cancel_events()
                return

            llm_messages = self._inject_authoritative_state(messages)
            response = self.llm.call(
                messages=llm_messages,
                tools=self.tools_schema,
                tool_choice="auto",
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            if response is None:
                yield {"type": "error", "content": "LLM 调用失败，请检查网络或 API Key"}
                yield {"type": "done"}
                return

            usage_obj = response.usage or Usage()
            usage = {
                "prompt_tokens": usage_obj.prompt_tokens,
                "completion_tokens": usage_obj.completion_tokens,
                "total_tokens": usage_obj.total_tokens,
            }
            round_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            round_usage["completion_tokens"] += usage.get("completion_tokens", 0)
            round_usage["total_tokens"] += usage.get("total_tokens", 0)

            # 更新精准 prompt_tokens 记录（用于压缩决策）
            self.last_precise_prompt_tokens = usage.get("prompt_tokens", 0)

            # 累积 token 使用到 session
            if self.session:
                self.session.add_token_usage(
                    usage["prompt_tokens"],
                    usage["completion_tokens"],
                    usage["total_tokens"]
                )
                # 保存 session 到文件
                SESSION_MGR._save_session(self.session.session_id)

                # 推送 token 更新事件到前端
                yield {
                    "type": "token_update",
                    "usage": usage,
                    "round_usage": round_usage.copy(),
                    "total_usage": self.session.token_usage.copy(),
                    "context_usage": self.session.context_usage.copy(),
                }

            if cancel_requested():
                yield from cancel_events()
                return

            finish_reason = response.finish_reason

            invalid_tool_call_error = self._invalid_tool_call_error(response.tool_calls)
            if invalid_tool_call_error:
                error_text = (
                    "模型返回了格式错误的工具调用参数，本轮工具调用已跳过，"
                    "并且不会写入 tool_calls 历史。请重试当前请求。"
                )
                msg_dict = {
                    "role": "assistant",
                    "content": error_text,
                }
                messages.append(msg_dict)
                self.messages = messages
                new_messages.append(msg_dict)
                if new_messages and new_messages[-1].get("role") == "assistant":
                    new_messages[-1]["usage"] = round_usage.copy()
                yield {"type": "error", "content": invalid_tool_call_error}
                yield {"type": "message_delta", "message": msg_dict}
                yield {"type": "new_messages", "messages": new_messages}
                yield {"type": "done"}
                return

            # 把 assistant 回复加入历史
            msg_dict = {"role": "assistant"}
            if response.content:
                msg_dict["content"] = response.content
            if response.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        },
                    }
                    for tc in response.tool_calls
                ]
            messages.append(msg_dict)
            self.messages = messages
            new_messages.append(msg_dict)

            # ── 情况 1：模型决定停止，输出最终答案 ────────────────────
            if finish_reason == "stop":
                final_text = response.content or ""

                # 输出最终答案
                # 如果 content 已有完整回答就直接推，否则再流式请求一次
                if final_text:
                    yield {"type": "final", "content": final_text}
                else:
                    # 极少数情况：content 为空但 finish_reason=stop，再流式请求
                    full = ""
                    stream_messages = messages[:]  # 包含完整 context
                    for event in self.llm.stream(
                        stream_messages, temperature=self.temperature
                    ):
                        if cancel_requested():
                            yield from cancel_events()
                            return
                        if event["type"] == "content":
                            full += event["content"]
                            yield {"type": "answer_chunk", "content": event["content"]}
                    final_text = full
                    yield {"type": "final", "content": full}

                # 追加最终 assistant 回复到 new_messages（已通过 msg_dict 追加过，此处修正 content）
                # msg_dict 已在上面加入 new_messages，但 content 可能为空，需修正最后一条
                if new_messages and new_messages[-1].get("role") == "assistant":
                    new_messages[-1]["content"] = final_text
                    new_messages[-1]["usage"] = round_usage.copy()

                yield {"type": "message_delta", "message": new_messages[-1]}

                yield {"type": "new_messages", "messages": new_messages}
                yield {"type": "done"}
                return

            # ── 情况 2：模型要调用工具 ──────────────────────────────────
            if finish_reason == "tool_calls" and response.tool_calls:
                yield {"type": "message_delta", "message": msg_dict}
                compacted_this_turn = False
                for tc in response.tool_calls:
                    tool_name = tc.name
                    args_json = tc.arguments or "{}"
                    call_id = tc.id
                    subagent_args = None
                    subagent_parse_error = None
                    if tool_name == "run_subagent":
                        try:
                            subagent_args = json.loads(args_json) if args_json.strip() else {}
                        except json.JSONDecodeError as e:
                            subagent_parse_error = e

                    # 给前端发送 tool_call 事件（预览参数摘要）
                    preview = args_json[:120] + ("…" if len(args_json) > 120 else "")
                    tool_event = {
                        "type": "tool_call",
                        "name": tool_name,
                        "input_preview": preview,
                        "call_id": call_id,
                    }
                    if tool_name == "run_subagent" and isinstance(subagent_args, dict):
                        task_val = subagent_args.get("task")
                        if isinstance(task_val, list):
                            tool_event["batch"] = True
                            tool_event["task_count"] = len(task_val)
                            tool_event["task"] = f"批量子任务 ({len(task_val)} 个)"
                        else:
                            tool_event["task"] = str(task_val or "")
                    yield tool_event

                    # Layer 3：检测 compact 工具调用
                    if tool_name == "compact":
                        # 执行 auto_compact（与 Layer 2 完全相同的流程）
                        messages = self.auto_compact(messages)
                        self.messages = messages
                        yield {"type": "context_snapshot", "messages": messages}
                        yield {"type": "compact", "content": "上下文已手动压缩"}
                        # compact 会重写上下文快照；其余工具让模型在下一轮重新决定。
                        compacted_this_turn = True
                        break

                    # 执行工具
                    if tool_name == "run_subagent":
                        result = yield from run_subagent_with_events(
                            subagent_args,
                            subagent_parse_error,
                            call_id,
                            self.llm_provider,
                            self.llm_model_id,
                        )
                    else:
                        result = self._execute_tool_call(tool_name, args_json)
                    print(f"[Tool] {tool_name} → {str(result)[:120]}")

                    # 推送 observation 事件
                    yield {"type": "observation", "content": result, "call_id": call_id}

                    # todo 工具：同步推 todo_update
                    if tool_name in {"todo", "todo_add", "todo_update", "todo_replan"}:
                        yield {"type": "todo_update", "items": list(self.todo.items)}

                    # 把工具结果追加到 messages
                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result,
                    }
                    messages.append(tool_msg)
                    self.messages = messages
                    new_messages.append(tool_msg)
                    yield {"type": "message_delta", "message": tool_msg}

                if compacted_this_turn:
                    if cancel_requested():
                        yield from cancel_events()
                        return
                    continue

                continue  # 继续下一轮，让模型观察结果

            # ── 情况 3：length（输出被截断）───────────────────────────
            if cancel_requested():
                yield from cancel_events()
                return

            if finish_reason == "length":
                if response.content and not response.tool_calls:
                    # 纯文本截断：直接将已生成内容作为最终答案输出。
                    # ❌ 不续写：续写会把更多 partial 消息堆入 context，
                    #            下一步 context 更大，最终导致 API context_length 错误。
                    final_text = response.content
                    # 修正 new_messages 里已追加的 assistant msg（content 可能为空）
                    if new_messages and new_messages[-1].get("role") == "assistant":
                        new_messages[-1]["content"] = final_text
                        new_messages[-1]["usage"] = round_usage.copy()
                    print(f"[Agent] step={step} 文本输出被截断，以现有内容作为最终答案")
                    yield {"type": "final", "content": final_text}
                    yield {"type": "message_delta", "message": new_messages[-1]}
                    yield {"type": "new_messages", "messages": new_messages}
                    yield {"type": "done"}
                    return
                # 工具调用参数被截断：JSON 不完整无法执行，报错退出
                yield {
                    "type": "error",
                    "content": (
                        "工具调用参数因 token 限制被截断，无法执行。"
                        f"当前 max_tokens={self.max_tokens}，"
                        "可在 config.yaml 中调高 agent.max_tokens"
                    ),
                }
                yield {"type": "new_messages", "messages": new_messages}
                yield {"type": "done"}
                return

            # ── 情况 4：其他意外 finish_reason ────────────────────────
            yield {
                "type": "error",
                "content": f"意外的 finish_reason: {finish_reason}",
            }
            yield {"type": "new_messages", "messages": new_messages}
            yield {"type": "done"}
            return

        yield {"type": "error", "content": f"已达到 max_steps={self.max_steps} 上限"}
        yield {"type": "new_messages", "messages": new_messages}
        yield {"type": "done"}

    def run(self, question: str) -> str:
        """阻塞式执行，返回最终答案字符串（CLI 使用）。"""
        final_text = ""
        for event in self.run_iter(question):
            t = event["type"]
            if t == "question":
                print(f"\n🤔 {event['content']}\n")
            elif t == "tool_call":
                print(f"\n[Tool Call] {event['name']}  {event['input_preview']}")
            elif t == "observation":
                print(f"[Observation] {event['content'][:200]}")
            elif t == "answer_chunk":
                print(event["content"], end="", flush=True)
            elif t == "final":
                final_text = event["content"]
                print(f"\n\n✅ 最终答案: {final_text[:200]}")
            elif t == "error":
                print(f"\n⚠️ {event['content']}")
                if not final_text:
                    final_text = f"（{event['content']}）"
        return final_text

    # ── 上下文压缩（三层策略已内联到 run_iter）──────────────────────────────
