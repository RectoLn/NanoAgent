"""
web_fetch 工具：获取 URL 的网页内容。

- 仅使用 Python 标准库（urllib, re, gzip, html）
- HTML 页面去除 <script>/<style> 标签及注释，提取纯文本
- 支持 gzip/deflate 解压
- 自动检测编码（Content-Type 优先，fallback utf-8）
- 结果截断至 8000 字符
"""

import gzip
import html
import re
import urllib.error
import urllib.request
from urllib.parse import urlparse

from registry import tool

_MAX_LEN = 8000
_TIMEOUT = 15
_UA = "Mozilla/5.0 (compatible; NanoAgent/0.1)"


def _decompress(data: bytes, encoding: str) -> bytes:
    """处理 gzip / deflate 响应体。"""
    enc = encoding.lower() if encoding else ""
    if enc == "gzip":
        return gzip.decompress(data)
    if enc == "deflate":
        import zlib
        try:
            return zlib.decompress(data)
        except zlib.error:
            return zlib.decompress(data, -15)
    return data


def _detect_charset(content_type: str, body: bytes) -> str:
    """从 Content-Type 或 HTML meta 中提取字符集。"""
    # 1. Content-Type: text/html; charset=utf-8
    m = re.search(r"charset\s*=\s*([^\s;\"']+)", content_type or "", re.I)
    if m:
        return m.group(1).strip()
    # 2. <meta charset="..."> 或 <meta http-equiv="Content-Type" ...>
    snippet = body[:4096].decode("ascii", errors="replace")
    m = re.search(r'<meta[^>]+charset\s*=\s*["\']?\s*([a-zA-Z0-9\-]+)', snippet, re.I)
    if m:
        return m.group(1).strip()
    return "utf-8"


def _strip_html(text: str) -> str:
    """去除 <script>/<style>/HTML 注释，提取可读文本。"""
    # 去除 <!-- ... --> 注释
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    # 去除 <script ...>...</script>
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.I)
    # 去除 <style ...>...</style>
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.I)
    # 块级标签后加换行
    text = re.sub(r"<(?:br|p|div|h[1-6]|li|tr|blockquote)[^>]*>", "\n", text, flags=re.I)
    # 去除所有剩余标签
    text = re.sub(r"<[^>]+>", "", text)
    # 反转义 HTML 实体（&amp; &lt; 等）
    text = html.unescape(text)
    # 合并连续空白行
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 合并每行内多余空格
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


@tool(
    name="web_fetch",
    description=(
        "获取指定 URL 的网页内容。"
        "HTML 页面会自动去除脚本/样式标签并提取纯文本；"
        "JSON/纯文本页面直接返回原始内容。"
        "结果截断至 8000 字符。超时 15 秒。"
    ),
)
def web_fetch(url: str = "") -> str:
    if not url or not url.strip():
        return "错误：未提供 URL"

    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"错误：仅支持 http/https 协议，收到：{parsed.scheme!r}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            content_type = resp.headers.get("Content-Type", "")
            content_encoding = resp.headers.get("Content-Encoding", "")
            status = resp.status
            raw = resp.read()
    except urllib.error.HTTPError as e:
        return f"HTTP 错误 {e.code}：{e.reason}（URL: {url}）"
    except urllib.error.URLError as e:
        return f"请求失败：{e.reason}（URL: {url}）"
    except Exception as e:
        return f"网络异常：{type(e).__name__}: {e}"

    # 解压
    try:
        raw = _decompress(raw, content_encoding)
    except Exception as e:
        return f"解压失败：{e}"

    # 解码
    charset = _detect_charset(content_type, raw)
    try:
        text = raw.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        text = raw.decode("utf-8", errors="replace")

    # HTML 提取纯文本
    ct_lower = content_type.lower()
    if "html" in ct_lower:
        text = _strip_html(text)
        prefix = f"[{status}] {url}\n\n"
    else:
        prefix = f"[{status}] {url} ({content_type})\n\n"

    result = prefix + text
    if len(result) > _MAX_LEN:
        result = result[:_MAX_LEN] + f"\n\n...（内容过长，已截断，原始长度 {len(result)} 字符）"

    return result
