"""
Context compression helpers for ToolCallAgent.

This module intentionally uses a mixin instead of a pure service object because
compression is part of the Agent's message-state lifecycle. Keeping the existing
`self` access avoids a large parameter object that would simply mirror the Agent.
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List

from app.prompt_loader import render_prompt
from session_state import (
    extract_state_from_messages,
    format_authoritative_state,
    merge_state,
)


class CompressionMixin:
    """
    Requires these attributes/methods from ToolCallAgent:
      self.session, self.todo, self.system_prompt, self.session_id
      self.comp_enabled, self.l1_*, self.l2_*
      self.summary_role, self.summary_prefix, self.compaction_hint
      self._new_summary_llm()
    """

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

        state_text = format_authoritative_state(getattr(self.session, "state", None))
        if state_text:
            new_messages.append({"role": "user", "content": state_text})

        summary_content = f"{self.summary_prefix}{summary}"
        new_messages.append({"role": self.summary_role, "content": summary_content})
        if self.compaction_hint:
            new_messages.append({"role": "user", "content": self.compaction_hint})

        if not self.todo.is_empty():
            task_status = (
                "[Current task status - authoritative]\n\n"
                f"{self.todo.render()}"
            )
            new_messages.append({"role": "user", "content": task_status})

        if latest_user and latest_user is not first_user:
            new_messages.append(latest_user)

        return new_messages

    def _summarize_tool_result(self, content: str) -> str:
        lines = [line.strip() for line in (content or "").splitlines() if line.strip()]
        if len(lines) <= 4:
            return (content or "")[:200]
        summary = "\n".join(lines[:3] + [f"...({len(lines)} lines total)", lines[-1]])
        return summary[:300]

    def _fallback_summary(self, messages: List[Dict]) -> str:
        """Build a deterministic summary when the LLM summarizer is unavailable."""
        previous_summaries: List[str] = []
        user_goals: List[str] = []
        assistant_notes: List[str] = []
        tool_notes: List[str] = []
        tool_call_names: List[str] = []

        for msg in messages:
            role = msg.get("role")
            content = (msg.get("content") or "").strip()
            if role == "user":
                if content.startswith(self.summary_prefix):
                    previous = content[len(self.summary_prefix):].strip()
                    if previous:
                        previous_summaries.append(re.sub(r"\s+", " ", previous)[:700])
                    continue
                if content.startswith((
                    "[Authoritative Session State]",
                    "[Current task status",
                    "[上下文摘要]",
                )):
                    continue
                if content:
                    user_goals.append(re.sub(r"\s+", " ", content)[:180])
            elif role == "assistant":
                for tc in msg.get("tool_calls") or []:
                    name = (tc.get("function") or {}).get("name")
                    if name:
                        tool_call_names.append(name)
                if content:
                    assistant_notes.append(re.sub(r"\s+", " ", content)[:180])
            elif role == "tool" and content:
                tool_notes.append(self._summarize_tool_result(content))

        lines = ["LLM 摘要生成失败，已使用本地规则生成兜底摘要。"]
        if previous_summaries:
            lines.append("既有摘要：" + "；".join(previous_summaries[-2:]))
        if user_goals:
            lines.append(f"用户目标：{user_goals[0]}")
        if len(user_goals) > 1:
            lines.append("近期用户补充：" + "；".join(user_goals[-3:]))
        if tool_call_names:
            names = list(dict.fromkeys(tool_call_names[-12:]))
            lines.append("已调用工具：" + "、".join(names))
        if assistant_notes:
            lines.append("执行进展：" + "；".join(assistant_notes[-4:]))
        if tool_notes:
            lines.append("关键观察：" + "；".join(tool_notes[-6:]))
        if not self.todo.is_empty():
            lines.append("当前任务状态：" + re.sub(r"\s+", " ", self.todo.render())[:500])

        return "\n".join(lines)[: max(self.l2_summary_max_chars, 1200)]

    def _is_parseable_summary_json(self, raw_summary: str) -> bool:
        if not raw_summary:
            return False
        try:
            json_text = re.sub(
                r"^\s*```(?:json)?\s*|\s*```\s*$",
                "",
                raw_summary,
                flags=re.I | re.S,
            ).strip()
            json.loads(json_text)
            return True
        except Exception:
            return False

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

        tool_entries = [(i, m) for i, m in enumerate(messages) if m.get("role") == "tool"]
        if len(tool_entries) <= self.l1_keep_recent:
            return messages

        call_id_to_name: Dict[str, str] = {}
        for msg in messages:
            for tc in msg.get("tool_calls") or []:
                cid = tc.get("id")
                name = (tc.get("function") or {}).get("name", "unknown")
                if cid:
                    call_id_to_name[cid] = name

        new_messages = list(messages)

        for idx, msg in tool_entries[:-self.l1_keep_recent]:
            content = (msg.get("content") or "").strip()
            if len(content) > self.l1_content_threshold:
                tc_id = msg.get("tool_call_id", "unknown")
                summary = self._summarize_tool_result(content)
                tool_name = call_id_to_name.get(tc_id, "unknown")
                new_messages[idx] = {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": (
                        f"[Compressed Tool Result | id: {tc_id}]\n"
                        f"summary: {summary}"
                    ),
                }
                if self.session:
                    state = getattr(self.session, "state", None) or {}
                    self.session.state = state
                    obs = state.setdefault("observations", {})
                    obs[tc_id] = {"summary": summary, "tool": tool_name}
        return new_messages

    def auto_compact(self, messages: List[Dict]) -> List[Dict]:
        """
        Layer 2 / Layer 3：自动压缩上下文。
        - 保存完整 messages 到 transcripts/（若配置开启）
        - 调用 LLM 生成摘要（使用 layer2.summary 配置）
        - 替换 messages 为压缩锚点消息集合
        返回 new_messages。
        """
        if not self.comp_enabled:
            return messages

        filename = None
        if self.l2_save_transcript and self.session_id:
            from tools.workspace import WORKSPACE_DIR

            transcripts_dir = WORKSPACE_DIR / "transcripts"
            transcripts_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = transcripts_dir / f"{self.session_id}_{timestamp}.jsonl"

            try:
                with open(filename, "w", encoding="utf-8") as f:
                    for msg in messages:
                        f.write(json.dumps(msg, ensure_ascii=False) + "\n")
            except Exception as e:
                print(f"[Compression] 保存 transcript 失败: {e}")

        from tools.summarize import format_messages_for_summary

        formatted = format_messages_for_summary(messages)
        formatted_original_chars = len(formatted)
        if (
            self.l2_summary_max_input_chars
            and self.l2_summary_max_input_chars > 0
            and len(formatted) > self.l2_summary_max_input_chars
        ):
            head_chars = int(self.l2_summary_max_input_chars * 0.45)
            tail_chars = self.l2_summary_max_input_chars - head_chars
            omitted_chars = len(formatted) - self.l2_summary_max_input_chars
            formatted = (
                formatted[:head_chars]
                + f"\n\n[Summary input truncated: omitted {omitted_chars} chars]\n\n"
                + formatted[-tail_chars:]
            )
        if self.l2_prompt_template:
            summary_prompt = render_prompt(self.l2_prompt_file, messages=formatted)
        else:
            summary_prompt = render_prompt(self.l2_fallback_prompt_file, messages=formatted)

        summary_prompt_chars = len(summary_prompt)
        summary_prompt_estimated_tokens = self.estimate_tokens([
            {"role": "user", "content": summary_prompt}
        ])
        summary_used_fallback = False
        summary_error = ""
        summary_finish_reason = ""
        summary_retry_used = False
        summary_retry_error = ""
        summary_retry_finish_reason = ""

        try:
            summary_llm = self._new_summary_llm()
            response = summary_llm.call(
                messages=[{"role": "user", "content": summary_prompt}],
                tools=None,
                temperature=self.l2_summary_temperature,
                max_tokens=self.l2_summary_max_tokens,
            )
            if self.session and response and response.usage:
                usage = response.usage
                self.session.add_token_usage(
                    usage.prompt_tokens,
                    usage.completion_tokens,
                    usage.total_tokens,
                    update_context=False,
                )
            if response:
                summary_finish_reason = str(response.finish_reason or "")
                raw_summary = (response.content or "").strip()
            else:
                summary_used_fallback = True
                summary_error = "LLM returned no response"
                raw_summary = self._fallback_summary(messages)
            if (
                summary_finish_reason == "length"
                and (not raw_summary or not self._is_parseable_summary_json(raw_summary))
            ):
                summary_retry_used = True
                retry_response = summary_llm.call(
                    messages=[{"role": "user", "content": summary_prompt}],
                    tools=None,
                    temperature=self.l2_summary_temperature,
                    max_tokens=self.l2_summary_retry_max_tokens,
                )
                if self.session and retry_response and retry_response.usage:
                    usage = retry_response.usage
                    self.session.add_token_usage(
                        usage.prompt_tokens,
                        usage.completion_tokens,
                        usage.total_tokens,
                        update_context=False,
                    )
                if retry_response:
                    summary_retry_finish_reason = str(retry_response.finish_reason or "")
                    raw_summary = (retry_response.content or "").strip()
                    if raw_summary:
                        summary_finish_reason = summary_retry_finish_reason or summary_finish_reason
                        summary_error = ""
                else:
                    summary_retry_error = "LLM summary retry returned no response"
            if (
                raw_summary
                and summary_finish_reason == "length"
                and not self._is_parseable_summary_json(raw_summary)
            ):
                summary_used_fallback = True
                summary_error = (
                    summary_retry_error
                    or "LLM returned truncated or invalid summary JSON"
                )
                raw_summary = self._fallback_summary(messages)
            if not raw_summary:
                summary_used_fallback = True
                summary_error = summary_error or summary_retry_error or "LLM returned empty summary content"
                raw_summary = self._fallback_summary(messages)
        except Exception as e:
            print(f"[Compression] 摘要生成异常: {e}")
            summary_used_fallback = True
            summary_error = str(e)
            raw_summary = self._fallback_summary(messages)

        progress_summary = raw_summary
        state_patch = {}
        file_knowledge = []
        try:
            json_text = re.sub(
                r"^\s*```(?:json)?\s*|\s*```\s*$",
                "",
                raw_summary,
                flags=re.I | re.S,
            ).strip()
            parsed_summary = json.loads(json_text)
            progress_summary = str(parsed_summary.get("progress_summary") or "").strip() or raw_summary
            state_patch = parsed_summary.get("state_patch") or {}
            if not isinstance(state_patch, dict):
                state_patch = {}
            file_knowledge = parsed_summary.get("file_knowledge") or []
            if not isinstance(file_knowledge, list):
                file_knowledge = []
        except Exception:
            progress_summary = raw_summary
            state_patch = {}
            file_knowledge = []

        summary = progress_summary

        if self.l2_summary_max_chars > 0 and len(summary) > self.l2_summary_max_chars:
            summary = summary[:self.l2_summary_max_chars] + "…"

        if self.session:
            rule_patch = extract_state_from_messages(messages)
            existing_texts = {
                re.sub(r"\s+", " ", str(item.get("text", ""))).strip().lower()
                for key in ("constraints", "facts", "invalidated_assumptions")
                for item in rule_patch.get(key, [])
            }
            for key in ("constraints", "facts", "invalidated_assumptions"):
                values = state_patch.get(key) or []
                if not isinstance(values, list):
                    continue
                for text in values:
                    dedupe_key = re.sub(r"\s+", " ", text).strip().lower() if isinstance(text, str) else ""
                    if dedupe_key and dedupe_key not in existing_texts:
                        existing_texts.add(dedupe_key)
                        rule_patch[key].append({"text": text.strip(), "source": "llm_inferred"})
            for item in file_knowledge:
                if not isinstance(item, dict):
                    continue
                path = (item.get("path") or "").strip()
                conclusion = (item.get("conclusion") or "").strip()
                if not path or not conclusion:
                    continue
                text = f"{path}: {conclusion}"
                dedupe_key = re.sub(r"\s+", " ", text).strip().lower()
                if dedupe_key not in existing_texts:
                    existing_texts.add(dedupe_key)
                    rule_patch["facts"].append({
                        "text": text,
                        "source": "llm_inferred",
                    })
            self.session.update_state(merge_state(getattr(self.session, "state", None), rule_patch))

        new_messages = self._build_compacted_messages(messages, summary)

        if self.session:
            token_saved = sum(len((m.get("content") or "").split()) for m in messages)
            record = {
                "timestamp": datetime.now().isoformat(),
                "transcript": str(filename) if filename else "",
                "original_count": len(messages),
                "compressed_count": len(new_messages),
                "token_saved": token_saved,
                "summary_used_fallback": summary_used_fallback,
                "summary_error": summary_error,
                "summary_finish_reason": summary_finish_reason,
                "summary_retry_used": summary_retry_used,
                "summary_retry_error": summary_retry_error,
                "summary_retry_finish_reason": summary_retry_finish_reason,
                "summary_retry_max_tokens": self.l2_summary_retry_max_tokens,
                "summary_input_chars": len(formatted),
                "summary_input_original_chars": formatted_original_chars,
                "summary_prompt_chars": summary_prompt_chars,
                "summary_prompt_estimated_tokens": summary_prompt_estimated_tokens,
                "summary": summary,
            }
            self.session.add_compression_record(record)

        return new_messages
