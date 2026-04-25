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
  error            错误
  done             结束
"""

import yaml
from datetime import datetime
from pathlib import Path
from typing import Generator, Dict, Any, List, Optional

from client import HelloAgentsLLM
from registry import execute_tool_call, TOOLS_SCHEMA
from todo_manager import TODO


def _load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_prompt(file_path: str) -> str:
    full_path = Path(__file__).parent / file_path
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read().strip()


class ToolCallAgent:
    """Tool Call 模式 Agent"""

    def __init__(self, llm: HelloAgentsLLM):
        self.llm = llm
        self.config = _load_config()

        agent_cfg = self.config.get("agent", {})
        self.max_steps = agent_cfg.get("max_steps", 30)
        self.temperature = agent_cfg.get("temperature", 0.1)
        self.max_tokens = agent_cfg.get("max_tokens", 16384)

        prompts_cfg = self.config.get("prompts", {})
        prompt_file = prompts_cfg.get("system", "prompts/system.md")
        self.system_prompt = _load_prompt(prompt_file)

    def run_iter(
        self,
        question: str,
        history: Optional[List[Dict]] = None,
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
          {"type": "new_messages", "messages": list} # 本轮新增消息（供 session 追加）
          {"type": "error",        "content": str}
          {"type": "done"}
        """
        yield {"type": "question", "content": question}

        # 如果有 history（含 system），直接使用并追加本轮 user 消息
        # 否则构建新对话
        if history is not None:
            messages: List[Dict] = list(history)
            # 压缩检查：在追加新用户消息之前，对已有历史执行压缩
            if self._should_compress_context(messages):
                messages, _log = self._compress_context(messages)
                if _log:
                    yield {"type": "compression_log", **_log}
            messages.append({"role": "user", "content": question})
        else:
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": question},
            ]

        # 记录本轮新增消息（不含历史），供 session 保存
        new_messages: List[Dict] = [{"role": "user", "content": question}]

        for step in range(1, self.max_steps + 1):
            # ── 请求模型（非流式，获取 tool_calls 或 stop）──────────────
            choice = self.llm.call(
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            if choice is None:
                yield {"type": "error", "content": "LLM 调用失败，请检查网络或 API Key"}
                yield {"type": "done"}
                return

            message = choice.message
            finish_reason = choice.finish_reason

            # 把 assistant 回复加入历史
            msg_dict = {"role": "assistant"}
            if message.content:
                msg_dict["content"] = message.content
            if message.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]
            messages.append(msg_dict)
            new_messages.append(msg_dict)

            # ── 情况 1：模型决定停止，输出最终答案 ────────────────────
            if finish_reason == "stop":
                final_text = message.content or ""

                # 输出最终答案
                # 如果 content 已有完整回答就直接推，否则再流式请求一次
                if final_text:
                    yield {"type": "final", "content": final_text}
                else:
                    # 极少数情况：content 为空但 finish_reason=stop，再流式请求
                    full = ""
                    stream_messages = messages[:]  # 包含完整 context
                    for event in self.llm.think_stream(
                        stream_messages, temperature=self.temperature
                    ):
                        if event["type"] == "content":
                            full += event["content"]
                            yield {"type": "answer_chunk", "content": event["content"]}
                    final_text = full
                    yield {"type": "final", "content": full}

                # 追加最终 assistant 回复到 new_messages（已通过 msg_dict 追加过，此处修正 content）
                # msg_dict 已在上面加入 new_messages，但 content 可能为空，需修正最后一条
                if new_messages and new_messages[-1].get("role") == "assistant":
                    new_messages[-1]["content"] = final_text

                yield {"type": "new_messages", "messages": new_messages}
                yield {"type": "done"}
                return

            # ── 情况 2：模型要调用工具 ──────────────────────────────────
            if finish_reason == "tool_calls" and message.tool_calls:
                for tc in message.tool_calls:
                    tool_name = tc.function.name
                    args_json = tc.function.arguments or "{}"
                    call_id = tc.id

                    # 给前端发送 tool_call 事件（预览参数摘要）
                    preview = args_json[:120] + ("…" if len(args_json) > 120 else "")
                    yield {
                        "type": "tool_call",
                        "name": tool_name,
                        "input_preview": preview,
                        "call_id": call_id,
                    }

                    # 执行工具
                    result = execute_tool_call(tool_name, args_json)
                    print(f"[Tool] {tool_name} → {str(result)[:120]}")

                    # 推送 observation 事件
                    yield {"type": "observation", "content": result, "call_id": call_id}

                    # todo 工具：同步推 todo_update
                    if tool_name == "todo":
                        yield {"type": "todo_update", "items": list(TODO.items)}

                    # 把工具结果追加到 messages
                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result,
                    }
                    messages.append(tool_msg)
                    new_messages.append(tool_msg)

                continue  # 继续下一轮，让模型观察结果

            # ── 情况 3：length（输出被截断）───────────────────────────
            if finish_reason == "length":
                if message.content and not message.tool_calls:
                    # 纯文本截断：直接将已生成内容作为最终答案输出。
                    # ❌ 不续写：续写会把更多 partial 消息堆入 context，
                    #            下一步 context 更大，最终导致 API context_length 错误。
                    final_text = message.content
                    # 修正 new_messages 里已追加的 assistant msg（content 可能为空）
                    if new_messages and new_messages[-1].get("role") == "assistant":
                        new_messages[-1]["content"] = final_text
                    print(f"[Agent] step={step} 文本输出被截断，以现有内容作为最终答案")
                    yield {"type": "final", "content": final_text}
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

    # ── 上下文压缩 ────────────────────────────────────────────────────────

    def _should_compress_context(self, history: List[Dict]) -> bool:
        """
        判断是否需要压缩，基于 config.yaml 中的 context 配置。
        仅统计非 system 消息的 token 估算值。
        """
        ctx_cfg = self.config.get("context", {})
        if not ctx_cfg.get("compression_enabled", True):
            return False

        token_threshold = ctx_cfg.get("compress_threshold_tokens", 25000)
        message_threshold = ctx_cfg.get("compress_threshold_messages", 50)

        non_system = [m for m in history if m.get("role") != "system"]
        token_estimate = sum(len((m.get("content") or "").split()) for m in non_system)
        return len(non_system) > message_threshold or token_estimate > token_threshold

    def _compress_context(self, history: List[Dict]):
        """
        压缩历史消息：保留 system prompt + 摘要消息 + 最近 N 条。

        返回 (new_history, log_data)。
        压缩失败时静默降级，返回 (原始 history, None)。
        """
        ctx_cfg = self.config.get("context", {})
        keep_recent = ctx_cfg.get("keep_recent_messages", 10)

        # system 消息单独提取
        system_msg = (
            history[0] if history and history[0].get("role") == "system" else None
        )
        rest = history[1:] if system_msg else history[:]

        if len(rest) <= keep_recent:
            return history, None  # 不足以压缩

        recent_msgs = rest[-keep_recent:]
        to_compress = rest[:-keep_recent]

        try:
            summary = self._summarize_messages(to_compress)
        except Exception as e:
            print(f"[Compression] 摘要生成异常，跳过压缩: {e}")
            return history, None

        token_saved = sum(len((m.get("content") or "").split()) for m in to_compress)

        summary_msg = {
            "role": "assistant",
            "content": f"[上下文摘要]\n{summary}",
        }

        new_history: List[Dict] = []
        if system_msg:
            new_history.append(system_msg)
        new_history.append(summary_msg)
        new_history.extend(recent_msgs)

        print(
            f"[Compression] {len(to_compress)} 条消息 → 摘要，"
            f"history {len(history)} → {len(new_history)}，"
            f"节省约 {token_saved} 词"
        )

        log_data = {
            "timestamp": datetime.now().isoformat(),
            "original_count": len(history),
            "compressed_count": len(new_history),
            "compressed_msg_count": len(to_compress),
            "token_saved": token_saved,
            "summary": summary,
        }
        return new_history, log_data

    def _summarize_messages(self, messages: List[Dict]) -> str:
        """调用 LLM 将消息段压缩为 Markdown 摘要（直接调用，不走 Tool Call 循环）。"""
        from tools.summarize import format_messages_for_summary

        formatted = format_messages_for_summary(messages)
        summary_prompt = (
            "请将以下对话历史压缩成一份简洁的摘要，保留关键决策、已获取的信息和重要结论：\n\n"
            f"{formatted}\n\n"
            "摘要要求：\n"
            "- 保留所有重要的数据和决策\n"
            "- 删除重复和冗长的推理过程\n"
            "- 以 Markdown 列表格式呈现\n"
            "- 最多 500 字"
        )

        choice = self.llm.call(
            messages=[{"role": "user", "content": summary_prompt}],
            tools=None,
            temperature=0.1,
        )

        if choice and choice.message and choice.message.content:
            return choice.message.content.strip()
        return "（摘要生成失败）"
