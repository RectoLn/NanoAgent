"""
Per-agent Todo manager.

The model should update tasks incrementally:
- todo_add: add one new item
- todo_update: change one existing item
- todo_replan: explicitly replace the list with a reason

The manager enforces small safety rules so context compression cannot easily
cause duplicate planning or parallel in-progress work.
"""

import re
from typing import Any, Dict, List, Optional


_VALID_STATUS = {"pending", "in_progress", "completed", "cancelled"}


class TodoManager:
    def __init__(self):
        self.items: List[Dict[str, Any]] = []

    def _fingerprint(self, item: Dict[str, Any]) -> str:
        text = str(item.get("text", "")).lower().replace("\\", "/")
        for old, new in (
            ("并整理", ""),
            ("完整", ""),
            ("内容", ""),
            ("了解布局结构", ""),
            (".pdf", ""),
            ("pdf", ""),
        ):
            text = text.replace(old, new)
        return re.sub(r"[\s`'\".,:;!?，。！？：；、（）()\[\]{}_-]+", "", text)

    def _is_same_task(self, a: Dict[str, Any], b: Dict[str, Any]) -> bool:
        a_key = self._fingerprint(a)
        b_key = self._fingerprint(b)
        if not a_key or not b_key:
            return False
        if a_key == b_key:
            return True
        shorter, longer = sorted((a_key, b_key), key=len)
        return len(shorter) >= 8 and shorter in longer

    def _has_unfinished_items(self) -> bool:
        return any(item.get("status") not in {"completed", "cancelled"} for item in self.items)

    def _validate_no_duplicates(self, items: List[Dict[str, Any]]) -> Optional[str]:
        seen_ids = set()
        seen_texts = set()
        for item in items:
            item_id = str(item.get("id", ""))
            text_key = self._fingerprint(item)
            if item_id in seen_ids:
                return f"Error: duplicate Todo id '{item_id}'"
            if text_key in seen_texts or any(self._is_same_task(item, existing) for existing in items[:items.index(item)]):
                return f"Error: duplicate Todo text '{item.get('text', '')}'. Use todo_update for existing tasks."
            seen_ids.add(item_id)
            seen_texts.add(text_key)
        return None

    def dedupe_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Best-effort cleanup for sessions saved before duplicate guards existed."""
        result: List[Dict[str, Any]] = []
        seen_ids = set()
        seen_texts = set()
        for item in items or []:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id", "")).strip()
            text = str(item.get("text", "")).strip()
            status = item.get("status", "pending")
            text_key = self._fingerprint({"text": text})
            if not item_id or not text_key or status not in _VALID_STATUS:
                continue
            if item_id in seen_ids or text_key in seen_texts or any(self._is_same_task({"text": text}, existing) for existing in result):
                continue
            seen_ids.add(item_id)
            seen_texts.add(text_key)
            result.append({"id": item_id, "text": text, "status": status})
        return result

    def update(self, items: List[Dict[str, Any]], *, allow_reset: bool = False) -> str:
        """
        Replace the full todo list.

        This remains for compatibility. Normal model use should prefer the
        incremental tools. If unfinished tasks exist, unrelated replacement is
        rejected unless allow_reset=True.
        """
        if not isinstance(items, list):
            return "Error: items must be a list"

        validated: List[Dict[str, Any]] = []
        in_progress_count = 0

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                return f"Error: item {idx} must be an object"
            item_id = str(item.get("id", idx + 1)).strip()
            text = str(item.get("text", "")).strip()
            status = item.get("status", "pending")

            if not item_id:
                return f"Error: item {idx} missing id"
            if not text:
                return f"Error: item {idx} missing text"
            if status not in _VALID_STATUS:
                return f"Error: invalid status '{status}', expected one of {sorted(_VALID_STATUS)}"
            if status == "in_progress":
                in_progress_count += 1

            validated.append({"id": item_id, "text": text, "status": status})

        if in_progress_count > 1:
            return "Error: only one Todo may be in_progress at a time"

        duplicate_error = self._validate_no_duplicates(validated)
        if duplicate_error:
            return duplicate_error

        if self.items and self._has_unfinished_items() and validated and not allow_reset:
            old_ids = {str(item.get("id")) for item in self.items}
            new_ids = {str(item.get("id")) for item in validated}
            old_texts = {self._fingerprint(item) for item in self.items}
            new_texts = {self._fingerprint(item) for item in validated}
            has_overlap = bool(old_ids & new_ids or old_texts & new_texts)
            if not has_overlap:
                return (
                    "Error: existing unfinished Todos cannot be silently replaced. "
                    "Use todo_update/todo_add, or todo_replan with a reason."
                )

        self.items = validated
        return self.render()

    def _next_id(self) -> str:
        used = {str(item.get("id")) for item in self.items}
        n = 1
        while str(n) in used:
            n += 1
        return str(n)

    def add_item(
        self,
        text: str,
        *,
        item_id: Optional[str] = None,
        status: str = "pending",
    ) -> str:
        """Add one todo item without replacing the existing list."""
        text = (text or "").strip()
        item_id = str(item_id).strip() if item_id is not None and str(item_id).strip() else self._next_id()

        if not text:
            return "Error: text cannot be empty"
        if status not in _VALID_STATUS:
            return f"Error: invalid status '{status}', expected one of {sorted(_VALID_STATUS)}"
        if any(str(item.get("id")) == item_id for item in self.items):
            return f"Error: Todo id '{item_id}' already exists"
        if any(self._is_same_task(item, {"text": text}) for item in self.items):
            return "Error: Todo already exists. Use todo_update to change its status or wording."
        if status == "in_progress" and any(item.get("status") == "in_progress" for item in self.items):
            return "Error: only one Todo may be in_progress at a time"

        self.items.append({"id": item_id, "text": text, "status": status})
        return self.render()

    def update_item(
        self,
        item_id: str,
        *,
        status: Optional[str] = None,
        text: Optional[str] = None,
    ) -> str:
        """Update one todo item by id."""
        item_id = str(item_id or "").strip()
        if not item_id:
            return "Error: id cannot be empty"

        target = None
        for item in self.items:
            if str(item.get("id")) == item_id:
                target = item
                break
        if target is None:
            return f"Error: Todo id '{item_id}' was not found"

        if status is not None and status != "":
            if status not in _VALID_STATUS:
                return f"Error: invalid status '{status}', expected one of {sorted(_VALID_STATUS)}"
            if status == "in_progress":
                for item in self.items:
                    if item is not target and item.get("status") == "in_progress":
                        return "Error: only one Todo may be in_progress at a time"
            target["status"] = status

        if text is not None and text != "":
            new_text = text.strip()
            if not new_text:
                return "Error: text cannot be empty"
            if any(item is not target and self._is_same_task(item, {"text": new_text}) for item in self.items):
                return "Error: another Todo with the same text already exists."
            target["text"] = new_text

        return self.render()

    def replan(self, items: List[Dict[str, Any]], *, reason: str) -> str:
        """Explicitly replace the todo list after the model provides a reason."""
        reason = (reason or "").strip()
        if not reason:
            return "Error: todo_replan requires a reason"
        rendered = self.update(items, allow_reset=True)
        if rendered.startswith("Error:"):
            return rendered
        return f"Todo replanned. Reason: {reason}\n{rendered}"

    def render(self) -> str:
        """Render a readable task list for the model and UI."""
        if not self.items:
            return "(todo list is empty)"
        icons = {
            "pending": "[ ]",
            "in_progress": "[>]",
            "completed": "[x]",
            "cancelled": "[-]",
        }
        lines = ["Current Todo list:"]
        for item in self.items:
            icon = icons.get(item["status"], "[?]")
            lines.append(f"  {icon} {item['id']}. {item['text']}")
        return "\n".join(lines)

    def is_empty(self) -> bool:
        return len(self.items) == 0

    def summary(self) -> str:
        """One-line summary for reminders."""
        if not self.items:
            return "(todo list is empty; create a plan before multi-step work)"
        total = len(self.items)
        done = sum(1 for item in self.items if item["status"] == "completed")
        in_progress = [item for item in self.items if item["status"] == "in_progress"]
        current = in_progress[0]["text"] if in_progress else "(none)"
        return f"Progress {done}/{total}; current: {current}"
