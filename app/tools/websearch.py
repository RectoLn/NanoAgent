"""
websearch 工具：使用 Tavily Search API 进行联网搜索。

- 仅依赖 Python 标准库
- 读取环境变量 TAVILY_API_KEY
- 缺少 API Key 时给出获取与配置提示
- 输出适合 Agent 阅读的 Markdown 风格搜索结果
"""

import json
import os
import urllib.error
import urllib.request
from typing import Any, Iterable, List

from registry import tool


_API_URL = "https://api.tavily.com/search"
_MAX_OUTPUT = 12000
_TIMEOUT = 30
_VALID_DEPTHS = {"ultra-fast", "fast", "basic", "advanced"}
_VALID_TOPICS = {"general", "news", "finance"}
_VALID_TIME_RANGES = {"day", "week", "month", "year", "d", "w", "m", "y"}


def _split_domains(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items: Iterable[Any] = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        raw_items = [value]
    return [str(item).strip() for item in raw_items if str(item).strip()]


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def _format_result(item: dict, index: int) -> str:
    title = str(item.get("title") or "Untitled").strip()
    url = str(item.get("url") or "").strip()
    content = str(item.get("content") or "").strip()
    score = item.get("score")
    published_date = str(item.get("published_date") or "").strip()

    suffix_parts = []
    if isinstance(score, (int, float)):
        suffix_parts.append(f"relevance: {score * 100:.0f}%")
    if published_date:
        suffix_parts.append(f"published: {published_date}")
    suffix = f" ({'; '.join(suffix_parts)})" if suffix_parts else ""

    lines = [f"{index}. {title}{suffix}"]
    if url:
        lines.append(f"   {url}")
    if content:
        lines.append(f"   {content[:700]}{'...' if len(content) > 700 else ''}")
    return "\n".join(lines)


def _format_response(data: dict, max_results: int) -> str:
    lines = [f"## Web Search: {data.get('query') or ''}".rstrip()]

    answer = str(data.get("answer") or "").strip()
    if answer:
        lines.extend(["", "### Answer", answer])

    results = data.get("results") or []
    if not isinstance(results, list):
        results = []

    lines.extend(["", f"### Sources ({min(len(results), max_results)} results)"])
    for index, item in enumerate(results[:max_results], start=1):
        if isinstance(item, dict):
            lines.extend(["", _format_result(item, index)])

    response_time = data.get("response_time")
    request_id = data.get("request_id")
    meta = []
    if response_time is not None:
        meta.append(f"response_time={response_time}s")
    if request_id:
        meta.append(f"request_id={request_id}")
    if meta:
        lines.extend(["", "### Meta", ", ".join(meta)])

    text = "\n".join(lines).strip()
    if len(text) > _MAX_OUTPUT:
        text = text[:_MAX_OUTPUT] + f"\n\n...（搜索结果过长，已截断，原始长度 {len(text)} 字符）"
    return text


@tool(
    name="websearch",
    description=(
        "使用 Tavily Search API 联网搜索，返回标题、URL、摘要、相关度和元数据。"
        "需要环境变量 TAVILY_API_KEY；缺少时会提示去 Tavily 官网获取并配置。"
    ),
)
def websearch(
    query: str = "",
    max_results: int = 5,
    search_depth: str = "basic",
    topic: str = "general",
    time_range: str = "",
    include_domains: Any = None,
    exclude_domains: Any = None,
    include_answer: bool = False,
    include_raw_content: bool = False,
) -> str:
    if not query or not query.strip():
        return "错误：未提供搜索 query"

    api_key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    if not api_key:
        return (
            "错误：未配置 TAVILY_API_KEY，无法联网搜索。\n"
            "请前往 Tavily 官网获取 API Key：https://tavily.com\n"
            "然后在 `.env` 中添加：TAVILY_API_KEY=tvly-你的密钥，并重启服务。"
        )

    max_results = _as_int(max_results, default=5, minimum=1, maximum=20)
    search_depth = (search_depth or "basic").strip()
    if search_depth not in _VALID_DEPTHS:
        return f"错误：search_depth 只能是 {sorted(_VALID_DEPTHS)}，收到：{search_depth!r}"

    topic = (topic or "general").strip()
    if topic not in _VALID_TOPICS:
        return f"错误：topic 只能是 {sorted(_VALID_TOPICS)}，收到：{topic!r}"

    body = {
        "query": query.strip(),
        "max_results": max_results,
        "search_depth": search_depth,
        "topic": topic,
        "include_answer": _as_bool(include_answer),
        "include_raw_content": _as_bool(include_raw_content),
    }

    time_range = (time_range or "").strip()
    if time_range:
        if time_range not in _VALID_TIME_RANGES:
            return f"错误：time_range 只能是 {sorted(_VALID_TIME_RANGES)}，收到：{time_range!r}"
        body["time_range"] = time_range

    include = _split_domains(include_domains)
    exclude = _split_domains(exclude_domains)
    if include:
        body["include_domains"] = include
    if exclude:
        body["exclude_domains"] = exclude

    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        _API_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "NanoAgent/0.8",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        if e.code == 401:
            return (
                "Tavily 鉴权失败：请检查 TAVILY_API_KEY 是否正确。\n"
                "可前往 https://tavily.com 重新获取 API Key。"
            )
        return f"Tavily 搜索失败（HTTP {e.code}）：{detail[:1000]}"
    except urllib.error.URLError as e:
        return f"Tavily 搜索请求失败：{e.reason}"
    except Exception as e:
        return f"Tavily 搜索异常：{type(e).__name__}: {e}"

    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        return f"Tavily 返回内容不是有效 JSON：{e}"

    return _format_response(data, max_results)
