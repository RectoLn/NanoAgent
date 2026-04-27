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
import yaml
from datetime import datetime
from pathlib import Path
from typing import Generator, Dict, Any, List, Optional

from client import HelloAgentsLLM
from registry import execute_tool_call, TOOLS_SCHEMA, set_thread_local_todo
from session_manager import SESSION_MGR
from todo_manager import TodoManager


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

    def __init__(self, llm: HelloAgentsLLM, session_id: Optional[str] = None, session = None):
        self.llm = llm
        self.config = _load_config()
        self.session_id = session_id
        self.session = session  # Session 对象引用，用于 compression_history

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
        self.l2_summary_max_chars = l2_summary.get("max_chars", 800)
        # Prompt 硬编码（无需配置）
        self.l2_prompt_template = (
            "请将以下对话历史压缩成一份简洁摘要，保留所有关键决策、"
            "已完成的操作、重要结论和当前进度，删除冗余推理过程。"
            "以 Markdown 列表格式输出，最多 800 字。\n\n"
            "{messages}"
        )
        # 总是保存 transcript（无需配置）
        self.l2_save_transcript = True

        # Layer 3: compact 工具（描述硬编码）
        self.l3_tool_description = "当你感到上下文过长影响推理时，主动调用此工具压缩上下文。"

        # 摘要消息格式（硬编码）
        self.summary_role = "user"
        self.summary_prefix = "[上下文摘要]\n\n"

        prompts_cfg = self.config.get("prompts", {})
        prompt_file = prompts_cfg.get("system", "prompts/system.md")
        self.system_prompt = _load_prompt(prompt_file)

        # 每个 Agent 持有独立的 TodoManager 实例（而非全局单例）
        self.todo = TodoManager()
        if self.session and getattr(self.session, "tasks", None):
            self.todo.items = [dict(item) for item in self.session.tasks]

    # ── 上下文压缩：三层策略 ──────────────────────────────────────────────────

    def estimate_tokens(self, messages: List[Dict]) -> int:
        """
        估算消息列表的 token 数（词数 × 1.3 系数）。
        仅统计 content 字段，忽略 tool_calls 等非文本字段。
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "") or ""
            text_cost = max(len(content.split()) * 1.3, len(content) / 4)
            total += text_cost
            if msg.get("tool_calls"):
                total += len(json.dumps(msg["tool_calls"], ensure_ascii=False)) / 4
            if msg.get("tool_call_id"):
                total += len(str(msg["tool_call_id"])) / 4
        return int(total)

    def _build_compacted_messages(self, messages: List[Dict], summary: str) -> List[Dict]:
        system_messages = [m for m in messages if m.get("role") == "system"]
        user_messages = [m for m in messages if m.get("role") == "user"]

        new_messages: List[Dict] = []
        if system_messages:
            new_messages.extend(system_messages)
        elif self.system_prompt:
            new_messages.append({"role": "system", "content": self.system_prompt})

        first_user = user_messages[0] if user_messages else None
        latest_user = user_messages[-1] if user_messages else None
        if first_user:
            new_messages.append(first_user)

        summary_content = f"{self.summary_prefix}{summary}"
        new_messages.append({"role": self.summary_role, "content": summary_content})

        if not self.todo.is_empty():
            task_status = (
                "[Current task status - authoritative]\n\n"
                f"{self.todo.render()}"
            )
            new_messages.append({"role": "user", "content": task_status})

        if latest_user and latest_user is not first_user:
            new_messages.append(latest_user)

        return new_messages

    def micro_compact(self, messages: List[Dict]) -> List[Dict]:
        """
        Layer 1：micro_compact - 每次 LLM 调用前静默执行。
        - 找出所有 role=="tool" 的消息
        - 保留最近 N 条 tool 消息不动（config: layer1.keep_recent_tool_messages）
        - 旧 tool 消息中，content 长度超过阈值的截断（config: layer1.content_threshold）
        返回新列表（不修改原列表）。
        """
        if not self.comp_enabled:
            return messages

        # 提取所有 tool 消息（索引, msg）
        tool_entries = [(i, m) for i, m in enumerate(messages) if m.get("role") == "tool"]
        if len(tool_entries) <= self.l1_keep_recent:
            return messages

        # 需要保留的索引集合（最近 N 条）
        new_messages = list(messages)  # 复制

        # 处理旧 tool 消息
        for idx, msg in tool_entries[:-self.l1_keep_recent]:
            content = (msg.get("content") or "").strip()
            if len(content) > self.l1_content_threshold:
                 tc_id = msg.get("tool_call_id", "unknown")
                 new_messages[idx] = {
                     "role": "tool",
                     "tool_call_id": tc_id,
                     "content": self.l1_placeholder_template.format(tool_call_id=tc_id),
                 }
        return new_messages

    def auto_compact(self, messages: List[Dict]) -> List[Dict]:
        """
        Layer 2 / Layer 3：自动压缩上下文。
        - 保存完整 messages 到 transcripts/（若配置开启）
        - 调用 LLM 生成摘要（使用 layer2.summary 配置）
        - 替换 messages 为单条摘要消息
        返回 new_messages。
        """
        if not self.comp_enabled:
            return messages

        # 1. 保存 transcript（可选）
        if self.l2_save_transcript and self.session_id:
            transcripts_dir = Path(__file__).parent.parent / "workspace" / "transcripts"
            transcripts_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = transcripts_dir / f"{self.session_id}_{timestamp}.jsonl"

            try:
                with open(filename, "w", encoding="utf-8") as f:
                    for msg in messages:
                        f.write(json.dumps(msg, ensure_ascii=False) + "\n")
            except Exception as e:
                print(f"[Compression] 保存 transcript 失败: {e}")

        # 2. 生成摘要
        from tools.summarize import format_messages_for_summary

        formatted = format_messages_for_summary(messages)
        summary_prompt = (
            self.l2_prompt_template or
            "请将以下对话历史压缩成一份简洁摘要，保留所有关键决策、"
            "已完成的操作、重要结论和当前进度，删除冗余推理过程。"
            "以 Markdown 列表格式输出，最多 800 字。\n\n"
        ) + formatted

        try:
            response = self.llm.call(
                messages=[{"role": "user", "content": summary_prompt}],
                tools=None,
                temperature=self.l2_summary_temperature,
                max_tokens=self.l2_summary_max_tokens,
            )
            if response and "choice" in response:
                choice = response["choice"]
                summary = (choice.message.content or "").strip()
            else:
                summary = "（摘要生成失败）"
            if not summary:
                summary = "（摘要生成失败）"
        except Exception as e:
            print(f"[Compression] 摘要生成异常: {e}")
            summary = "（摘要生成失败）"

        # 截断摘要长度
        if self.l2_summary_max_chars > 0 and len(summary) > self.l2_summary_max_chars:
            summary = summary[:self.l2_summary_max_chars] + "…"

        # 3. 替换 messages
        new_messages = self._build_compacted_messages(messages, summary)

        # 4. 记录 compression_history
        if self.session:
            token_saved = sum(len((m.get("content") or "").split()) for m in messages)
            record = {
                "timestamp": datetime.now().isoformat(),
                "transcript": str(filename) if self.l2_save_transcript and self.session_id else "",
                "original_count": len(messages),
                "compressed_count": len(new_messages),
                "token_saved": token_saved,
                "summary": summary,
            }
            self.session.add_compression_record(record)

        return new_messages

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
            messages.append({"role": "user", "content": question})
        else:
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": question},
            ]

        # 记录本轮新增消息（不含历史），供 session 保存
        new_messages: List[Dict] = [{"role": "user", "content": question}]
        round_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        for step in range(1, self.max_steps + 1):
            # ── Layer 1：micro_compact 每次 LLM 调用前静默执行 ─────────────
            messages = self.micro_compact(messages)

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
                    # 重置精准计数（压缩后历史已变，旧值不再适用）
                    self.last_precise_prompt_tokens = None
                    yield {"type": "compact", "content": "上下文已自动压缩"}

            # ── 注入当前 Agent 的 TodoManager 和 Session 到线程局部，供工具函数访问 ──
            set_thread_local_todo(self.todo, self.session)

            # ── 请求模型（非流式，获取 tool_calls 或 stop）──────────────
            response = self.llm.call(
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            if response is None:
                yield {"type": "error", "content": "LLM 调用失败，请检查网络或 API Key"}
                yield {"type": "done"}
                return

            choice = response["choice"]
            usage = response["usage"]
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
                    new_messages[-1]["usage"] = round_usage.copy()

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

                    # Layer 3：检测 compact 工具调用
                    if tool_name == "compact":
                        # 执行 auto_compact（与 Layer 2 完全相同的流程）
                        messages = self.auto_compact(messages)
                        yield {"type": "compact", "content": "上下文已手动压缩"}
                        # compact 工具不产生 tool_msg，直接进入下一轮
                        continue

                    # 执行工具
                    result = execute_tool_call(tool_name, args_json)
                    print(f"[Tool] {tool_name} → {str(result)[:120]}")

                    # 推送 observation 事件
                    yield {"type": "observation", "content": result, "call_id": call_id}

                    # todo 工具：同步推 todo_update
                    if tool_name == "todo":
                        yield {"type": "todo_update", "items": list(self.todo.items)}

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
                        new_messages[-1]["usage"] = round_usage.copy()
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

    # ── 上下文压缩（三层策略已内联到 run_iter）──────────────────────────────
