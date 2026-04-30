"""
Session state utilities.

This module stores durable, structured context that should survive
conversation compaction. Keep it conservative: state should preserve
user constraints, verified facts, and explicitly invalidated assumptions.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Iterable, List


STATE_VERSION = 1
STATE_KEYS = ("constraints", "facts", "invalidated_assumptions")
SOURCE_PRIORITY = {
    "user": 4,
    "tool_verified": 3,
    "user_fact": 2,
    "llm_inferred": 1,
    "session": 0,
}

CONSTRAINT_PATTERNS = (
    "必须",
    "严格",
    "只能",
    "不要",
    "不能",
    "不允许",
    "不参考",
    "只参考",
    "基于",
    "来源",
    "真实",
    "PDF",
    "pdf",
)

INVALIDATION_PATTERNS = (
    "不对",
    "错了",
    "搞错",
    "不是",
    "真实在哪",
    "别用",
    "不能用",
    "不要用",
    "虚构",
)

FACT_PATTERNS = ()


def _now() -> str:
    return datetime.now().isoformat()


def default_state() -> Dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "constraints": [],
        "facts": [],
        "invalidated_assumptions": [],
        "observations": {},
    }


def _slug_prefix(key: str) -> str:
    return {
        "constraints": "c",
        "facts": "f",
        "invalidated_assumptions": "i",
    }.get(key, "s")


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _dedupe_key(value: Any) -> str:
    text = _normalize_text(value).lower()
    text = re.sub(r"\[source:[^\]]+\]", "", text)
    text = re.sub(r"（[^）]*）|\([^)]*\)", "", text)
    text = text.replace("\\", "/")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[`'\"“”‘’（）()，,。.:：；;、\-_\s]+", "", text)
    replacements = (
        ("必须遵循", "遵循"),
        ("必须使用", "使用"),
        ("严格使用", "使用"),
        ("而非其他pptskill", ""),
        ("为林子越简历pdf生成幻灯片", "生成幻灯片"),
        ("为林子越简历.pdf生成幻灯片", "生成幻灯片"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _find_equivalent_item(items: List[Dict[str, Any]], dedupe_key: str) -> Dict[str, Any] | None:
    if not dedupe_key:
        return None
    for item in items:
        existing_key = _dedupe_key(item.get("text"))
        if not existing_key:
            continue
        if existing_key == dedupe_key:
            return item
        shorter, longer = sorted((existing_key, dedupe_key), key=len)
        if len(shorter) >= 18 and shorter in longer:
            return item
    return None


def _item_text(item: Any) -> str:
    if isinstance(item, dict):
        return _normalize_text(item.get("text") or item.get("content") or "")
    return _normalize_text(item)


def _normalize_item(item: Any, key: str, index: int) -> Dict[str, Any] | None:
    text = _item_text(item)
    if not text:
        return None

    if isinstance(item, dict):
        normalized = dict(item)
    else:
        normalized = {"text": text}

    normalized["text"] = text
    normalized.setdefault("id", f"{_slug_prefix(key)}_{index + 1:03d}")
    normalized.setdefault("source", "session")
    normalized.setdefault("created_at", _now())
    normalized.setdefault("status", "active")

    if key == "facts":
        normalized.setdefault("verified", False)

    return normalized


def normalize_state(state: Any) -> Dict[str, Any]:
    normalized = default_state()
    if not isinstance(state, dict):
        return normalized

    normalized["version"] = int(state.get("version") or STATE_VERSION)
    observations = state.get("observations") or {}
    normalized["observations"] = observations if isinstance(observations, dict) else {}
    if len(normalized["observations"]) > 80:
        normalized["observations"] = dict(list(normalized["observations"].items())[-80:])
    for key in STATE_KEYS:
        raw_items = state.get(key) or []
        if not isinstance(raw_items, list):
            raw_items = []
        items: List[Dict[str, Any]] = []
        seen = set()
        for index, raw in enumerate(raw_items):
            item = _normalize_item(raw, key, index)
            if not item:
                continue
            dedupe_key = _dedupe_key(item["text"])
            if dedupe_key in seen or _find_equivalent_item(items, dedupe_key):
                continue
            seen.add(dedupe_key)
            items.append(item)
        normalized[key] = items

    constraint_keys = {
        _dedupe_key(item.get("text"))
        for item in normalized["constraints"]
        if _dedupe_key(item.get("text"))
    }
    if constraint_keys:
        normalized["invalidated_assumptions"] = [
            item for item in normalized["invalidated_assumptions"]
            if _dedupe_key(item.get("text")) not in constraint_keys
        ]

    return normalized


def merge_state(base: Any, patch: Any) -> Dict[str, Any]:
    merged = normalize_state(base)
    incoming = normalize_state(patch)

    for key in STATE_KEYS:
        for item in incoming[key]:
            dedupe_key = _dedupe_key(item.get("text"))
            if not dedupe_key:
                continue
            existing = _find_equivalent_item(merged[key], dedupe_key)
            if existing:
                # Preserve the strongest source when duplicate text appears.
                old_priority = SOURCE_PRIORITY.get(existing.get("source", "session"), 0)
                new_priority = SOURCE_PRIORITY.get(item.get("source", "session"), 0)
                if new_priority > old_priority:
                    existing["source"] = item.get("source", existing.get("source"))
                continue
            merged[key].append(item)

    merged["observations"].update(incoming.get("observations", {}))
    if len(merged["observations"]) > 80:
        merged["observations"] = dict(list(merged["observations"].items())[-80:])

    merged["version"] = max(int(merged.get("version", 1)), int(incoming.get("version", 1)))
    return merged


def is_state_empty(state: Any) -> bool:
    normalized = normalize_state(state)
    return not any(normalized[key] for key in STATE_KEYS) and not normalized.get("observations")


def _split_candidate_lines(text: str) -> Iterable[str]:
    for raw in re.split(r"[\n。！？!?]+", text or ""):
        line = _normalize_text(raw)
        if not line:
            continue
        if len(line) > 260:
            line = line[:260].rstrip() + "..."
        yield line


def _contains_any(text: str, patterns: Iterable[str]) -> bool:
    return any(pattern in text for pattern in patterns)


def extract_state_from_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a conservative state patch from a single message."""
    role = message.get("role")
    content = message.get("content") or ""
    patch = default_state()
    if not isinstance(content, str) or not content.strip():
        return patch
    if content.startswith((
        "[上下文摘要]",
        "[Current task status",
        "[Authoritative Session State]",
    )):
        return patch

    timestamp = _now()

    if role == "user":
        for line in _split_candidate_lines(content):
            if _contains_any(line, CONSTRAINT_PATTERNS):
                patch["constraints"].append({
                    "text": line,
                    "source": "user",
                    "created_at": timestamp,
                    "status": "active",
                })
            if _contains_any(line, INVALIDATION_PATTERNS):
                patch["invalidated_assumptions"].append({
                    "text": line,
                    "source": "user",
                    "reason": "用户明确纠正或否定了先前上下文",
                    "created_at": timestamp,
                    "status": "active",
                })
            elif _contains_any(line, FACT_PATTERNS) and ("：" in line or ":" in line) and len(line) <= 180:
                patch["facts"].append({
                    "text": line,
                    "source": "user",
                    "created_at": timestamp,
                    "status": "active",
                    "verified": False,
                })

    return patch


def extract_state_from_messages(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    patch = default_state()
    for message in messages:
        patch = merge_state(patch, extract_state_from_message(message))
    return patch


def format_authoritative_state(state: Any, max_items: int = 8) -> str:
    normalized = normalize_state(state)
    if is_state_empty(normalized):
        return ""

    lines = [
        "[Authoritative Session State]",
        "以下结构化状态优先级高于压缩摘要；遇到冲突时，以 active constraints / facts / invalidated_assumptions 为准。",
        "",
    ]

    labels = {
        "constraints": "constraints",
        "facts": "facts",
        "invalidated_assumptions": "invalidated_assumptions",
    }
    for key in STATE_KEYS:
        items = [
            item for item in normalized[key]
            if item.get("status", "active") == "active"
        ][:max_items]
        lines.append(f"{labels[key]}:")
        if not items:
            lines.append("- (none)")
        else:
            for item in items:
                suffix = ""
                source = item.get("source")
                if source:
                    suffix = f" [source: {source}]"
                lines.append(f"- {item.get('text')}{suffix}")
        lines.append("")

    observations = normalized.get("observations") or {}
    if observations:
        lines.append("observations:")
        for obs_id, obs in list(observations.items())[-5:]:
            if not isinstance(obs, dict):
                continue
            tool_name = obs.get("tool", "unknown")
            summary = _normalize_text(obs.get("summary", ""))[:120]
            lines.append(f"- [{obs_id}] {tool_name}: {summary}")
        lines.append("")

    return "\n".join(lines).strip()
