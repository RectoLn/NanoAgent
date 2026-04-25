"""
消息摘要工具 - 上下文压缩辅助模块。

仅供 agent.py 内部调用，不注册为 LLM 可见工具。
原因：压缩是透明的自动操作，由 Agent 主动触发，LLM 不应感知。
"""

from typing import List, Dict


def format_messages_for_summary(messages: List[Dict]) -> str:
    """
    将消息列表格式化为可读文本，供 LLM 生成摘要。

    - user 消息：直接显示内容（截断至 600 字符）
    - assistant 消息：显示工具调用名+参数摘要，以及文本内容
    - tool 消息：显示工具返回结果摘要（截断至 300 字符）
    """
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = (msg.get("content") or "").strip()

        if role == "user":
            lines.append(f"[用户] {content[:600]}")

        elif role == "assistant":
            tool_calls = msg.get("tool_calls") or []
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", "")[:200]
                lines.append(f"[Assistant→工具] {name}({args})")
            if content:
                lines.append(f"[Assistant] {content[:600]}")

        elif role == "tool":
            lines.append(f"[工具结果] {content[:300]}")

    return "\n".join(lines)
