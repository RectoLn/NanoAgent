"""
TodoManager：带状态的任务列表，供 Agent 规划多步任务。

- 状态：pending / in_progress / completed / cancelled
- 约束：同一时间最多 1 个 in_progress（强制顺序聚焦）
- 全局单例：整个 Agent 会话共享同一张 todo list
"""

from typing import List, Dict, Any


_VALID_STATUS = {"pending", "in_progress", "completed", "cancelled"}


class TodoManager:
    def __init__(self):
        self.items: List[Dict[str, Any]] = []

    def update(self, items: List[Dict[str, Any]]) -> str:
        """
        整体替换 todo list。
        items: [{"id": "1", "text": "...", "status": "pending"}, ...]
        """
        if not isinstance(items, list):
            return "错误：items 必须是列表"

        validated: List[Dict[str, Any]] = []
        in_progress_count = 0

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                return f"错误：第 {idx} 项不是对象"
            item_id = str(item.get("id", idx + 1))
            text = item.get("text", "").strip()
            status = item.get("status", "pending")

            if not text:
                return f"错误：第 {idx} 项缺少 text"
            if status not in _VALID_STATUS:
                return f"错误：第 {idx} 项 status='{status}' 非法，应为 {sorted(_VALID_STATUS)}"
            if status == "in_progress":
                in_progress_count += 1

            validated.append({"id": item_id, "text": text, "status": status})

        if in_progress_count > 1:
            return "错误：同一时间只允许 1 个 in_progress 任务"

        self.items = validated
        return self.render()

    def render(self) -> str:
        """渲染为可读字符串，供 Agent 查看或注入 reminder。"""
        if not self.items:
            return "（todo 列表为空）"
        icons = {
            "pending": "[ ]",
            "in_progress": "[>]",
            "completed": "[x]",
            "cancelled": "[-]",
        }
        lines = ["当前 Todo 列表："]
        for it in self.items:
            icon = icons.get(it["status"], "[?]")
            lines.append(f"  {icon} {it['id']}. {it['text']}")
        return "\n".join(lines)

    def is_empty(self) -> bool:
        return len(self.items) == 0

    def summary(self) -> str:
        """一行摘要，用于 reminder。"""
        if not self.items:
            return "（todo 列表为空，请先用 todo 工具制定计划）"
        total = len(self.items)
        done = sum(1 for i in self.items if i["status"] == "completed")
        in_progress = [i for i in self.items if i["status"] == "in_progress"]
        current = in_progress[0]["text"] if in_progress else "（无进行中）"
        return f"进度 {done}/{total}；当前：{current}"


# 全局单例
TODO = TodoManager()
