"""
Telegram Bot 通道封装（Long Polling 主模式，Webhook 备用）。

本地测试（无需 ngrok）：
1. 在 .env 中配置：
       TELEGRAM_BOT_TOKEN=你的BotToken
       TELEGRAM_POLLING_ENABLED=true   # 必须显式开启

2. 启动服务：
       uvicorn app.server:app --port 8000

3. 观察日志出现：
       Telegram polling started

4. 打开 Telegram，向 Bot 发任意文字消息。
   Bot 会先回复 "⏳ 处理中..."，Agent 处理完成后回复最终结果。

注意：TELEGRAM_POLLING_ENABLED 默认关闭，需在目标实例上显式设为 true，
      避免多实例共享同一 token 时互相抢占 updates。
"""

import asyncio
import os
import re
from typing import Awaitable, Callable

import httpx

_API = "https://api.telegram.org/bot{token}/{method}"
_MAX_MSG_LEN = 4096


def _token() -> str | None:
    """延迟读取，避免模块加载时 .env 尚未完全注入。"""
    return os.getenv("TELEGRAM_BOT_TOKEN")


def _polling_enabled() -> bool:
    """只有 TELEGRAM_POLLING_ENABLED=true 时才允许 Long Polling 启动。"""
    return os.getenv("TELEGRAM_POLLING_ENABLED", "").lower() == "true"


def _url(method: str) -> str:
    return _API.format(token=_token(), method=method)


# ── Markdown → Telegram MarkdownV2 转换 ───────────────────────────────────

# MarkdownV2 所有需要转义的特殊字符
_V2_SPECIAL = r"\_*[]()~`>#+=|{}.!-"


def _escape_v2(text: str) -> str:
    """转义 MarkdownV2 所有特殊字符（普通文本使用）。"""
    out = []
    for ch in text:
        if ch in _V2_SPECIAL:
            out.append(f"\\{ch}")
        else:
            out.append(ch)
    return "".join(out)


def _escape_code_v2(text: str) -> str:
    """代码内容只转义反斜杠和反引号（MarkdownV2 代码块规则）。"""
    return text.replace("\\", "\\\\").replace("`", "\\`")


def _process_inline_v2(text: str) -> str:
    """
    处理行内格式，输出 MarkdownV2。
    顺序：先按行内代码拆分保护代码内容，再对普通文本做转义+格式标记。
    """
    out = []
    # 按行内代码拆分
    parts = re.split(r"(`[^`\n]+`)", text)
    for part in parts:
        if part.startswith("`") and part.endswith("`") and len(part) > 2:
            inner = _escape_code_v2(part[1:-1])
            out.append(f"`{inner}`")
            continue

        # 提取粗体/斜体 token，其余字符按位转义
        # 策略：先识别 **...** 和 *...* 区域，其余全部 _escape_v2
        segments: list[str] = []
        remaining = part
        pattern = re.compile(r"(\*\*(.+?)\*\*|\*(.+?)\*|__(.+?)__)")
        last = 0
        for m in pattern.finditer(remaining):
            # 转义 match 前的普通文本
            segments.append(_escape_v2(remaining[last : m.start()]))
            raw = m.group(0)
            if raw.startswith("**") or raw.startswith("__"):
                inner_text = m.group(2) or m.group(4)
                segments.append(f"*{_escape_v2(inner_text)}*")  # V2 粗体用单 *
            else:
                inner_text = m.group(3)
                segments.append(f"_{_escape_v2(inner_text)}_")  # V2 斜体用 _
            last = m.end()
        segments.append(_escape_v2(remaining[last:]))
        out.append("".join(segments))
    return "".join(out)


def _md_to_markdownv2(text: str) -> str:
    """
    完整 Markdown → Telegram MarkdownV2 转换。

    支持：
      - 围栏代码块  ```lang\\n...```  →  ```lang\\n...```  (V2 格式)
      - 标题        ## Title          →  *Title*  (粗体)
      - 表格        | col | ...       →  ``` 等宽代码块 ```
      - 无序列表    - item / * item   →  • item
      - 有序列表    1. item           →  1\\. item  (转义点号)
      - 粗体        **text**          →  *text*
      - 斜体        *text*            →  _text_
      - 行内代码    `text`            →  `text`
    """
    out = []

    # 第一步：按围栏代码块拆分（最高优先级）
    fence_re = re.compile(r"(```[^\n]*\n[\s\S]*?```)", re.DOTALL)
    segments = fence_re.split(text)

    for seg in segments:
        # 围栏代码块：内容只转义 \ 和 `；不带语言标识，避免 Telegram 解析异常
        if seg.startswith("```"):
            m = re.match(r"```([^\n]*)\n([\s\S]*?)```", seg, re.DOTALL)
            if m:
                body = _escape_code_v2(m.group(2).rstrip("\n"))
                out.append(f"```\n{body}\n```")
            else:
                out.append(f"```\n{_escape_code_v2(seg[3:-3])}\n```")
            continue

        # 第二步：逐行处理
        lines = seg.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]

            # 标题行
            hdr = re.match(r"^(#{1,6})\s+(.+)$", line)
            if hdr:
                level = len(hdr.group(1))
                title = _escape_v2(hdr.group(2))
                if level <= 2:
                    out.append(f"\n*{title}*\n")
                else:
                    out.append(f"\n*_{title}_*\n")
                i += 1
                continue

            # 表格块：连续以 | 开头的行 → 等宽代码块（先剥离行内格式）
            if line.strip().startswith("|"):
                table_lines = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    stripped = lines[i].strip()
                    # 跳过纯分隔行
                    if not re.match(r"^[\|\-\:\s]+$", stripped):
                        table_lines.append(lines[i])
                    i += 1
                if table_lines:
                    # Strip inline markdown (**bold**, *italic*, `code`) from each cell
                    def strip_inline_md(s: str) -> str:
                        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)  # **bold**
                        s = re.sub(r"\*(.+?)\*", r"\1", s)  # *italic*
                        s = re.sub(r"`(.+?)`", r"\1", s)  # `code`
                        return s

                    cleaned = [strip_inline_md(l) for l in table_lines]
                    # 代码块内容直接输出，不做转义（已经是纯文本）
                    out.append("```\n" + "\n".join(cleaned) + "\n```\n")
                continue

            # 无序列表
            ul = re.match(r"^(\s*)[-*+]\s+(.+)$", line)
            if ul:
                indent = len(ul.group(1)) // 2
                bullet = "  " * indent + "•"
                out.append(f"{bullet} {_process_inline_v2(ul.group(2))}\n")
                i += 1
                continue

            # 有序列表
            ol = re.match(r"^(\s*)(\d+)\.\s+(.+)$", line)
            if ol:
                indent = len(ol.group(1)) // 2
                num = ol.group(2)
                prefix = "  " * indent + f"{num}\\."
                out.append(f"{prefix} {_process_inline_v2(ol.group(3))}\n")
                i += 1
                continue

            # 普通行
            out.append(_process_inline_v2(line) + "\n")
            i += 1

    return "".join(out)


def _md_to_html_simple(text: str) -> str:
    """
    极简 HTML 转换，仅作 MarkdownV2 失败后的降级备用。
    只处理：& < > 转义 + **bold** + `code`，其余原样输出。
    """

    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    out = []
    for part in re.split(r"(`[^`\n]+`)", text):
        if part.startswith("`") and part.endswith("`") and len(part) > 2:
            out.append(f"<code>{esc(part[1:-1])}</code>")
        else:
            p = esc(part)
            p = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", p)
            out.append(p)
    return "".join(out)


# ── 输入状态指示 ──────────────────────────────────────────────────────────────


async def send_chat_action(chat_id: int | str, action: str = "typing") -> None:
    """
    发送聊天动作（正在输入状态）。

    action 可选值：
      - typing          正在输入
      - upload_photo    正在上传照片
      - record_video    正在录制视频
      - upload_document 正在上传文档
      等等

    Telegram 会显示对应状态，持续约 5 秒。
    可间隔调用维持持续显示（通常不需要）。
    """
    if not _token():
        return

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                _url("sendChatAction"),
                json={"chat_id": chat_id, "action": action},
                timeout=5,
            )
    except Exception as e:
        print(f"[channel/telegram] 发送输入状态失败: {e}")


# ── 发送消息 ───────────────────────────────────────────────────────────────


def _make_attempts(text: str) -> list[tuple[str | None, str]]:
    """
    构建三级降级尝试列表：(parse_mode, payload_text)
      1. MarkdownV2  — 完整格式
      2. HTML        — 极简格式（降级备用）
      3. None        — 纯文本（最终兜底）
    """
    v2_text = _md_to_markdownv2(text)
    html_text = _md_to_html_simple(text)
    plain_text = text
    return [
        ("MarkdownV2", v2_text),
        ("HTML", html_text),
        (None, plain_text),
    ]


def _split_chunks(text: str, max_len: int = _MAX_MSG_LEN) -> list[str]:
    """按 max_len 分段，保证至少一段。"""
    return [text[i : i + max_len] for i in range(0, len(text), max_len)] or [""]


async def send_message(chat_id: int | str, text: str) -> None:
    """
    向指定 chat_id 发送文字消息。

    降级链：MarkdownV2 → HTML → 纯文本
    每级失败（400）时打印日志并自动尝试下一级。
    超过 4096 字符自动分段（每段独立降级）。
    """
    if not _token():
        print(f"[channel/telegram] 无法发送消息（Token 未设置）: {text[:80]}")
        return

    attempts = _make_attempts(text)

    async with httpx.AsyncClient() as client:
        # 以第一级（MarkdownV2）的分段数量为基准
        # 各级文本长度可能不同，分别按自身 max_len 分段
        chunk_count = max(len(_split_chunks(t)) for _, t in attempts)

        for chunk_idx in range(chunk_count):
            sent = False
            for parse_mode, full_text in attempts:
                chunks = _split_chunks(full_text)
                chunk = chunks[chunk_idx] if chunk_idx < len(chunks) else chunks[-1]
                payload: dict = {"chat_id": chat_id, "text": chunk}
                if parse_mode:
                    payload["parse_mode"] = parse_mode
                try:
                    resp = await client.post(
                        _url("sendMessage"), json=payload, timeout=10
                    )
                    resp.raise_for_status()
                    sent = True
                    break  # 成功，不再降级
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 400 and parse_mode:
                        print(
                            f"[channel/telegram] {parse_mode} 解析失败，降级: {e.response.text[:120]}"
                        )
                        continue
                    print(f"[channel/telegram] 发送消息失败 ({parse_mode}): {e}")
                    break
                except Exception as e:
                    print(f"[channel/telegram] 发送消息失败: {e}")
                    break
            if not sent:
                print(f"[channel/telegram] 第 {chunk_idx + 1} 段三级降级均失败，放弃")


# ── Long Polling ───────────────────────────────────────────────────────────


async def start_polling(
    on_message: Callable[[int, str], Awaitable[None]],
) -> None:
    """
    Long Polling 主循环。

    参数：
        on_message(chat_id, text) — 收到文字消息时的回调协程

    行为：
    - 仅当 TELEGRAM_POLLING_ENABLED=true 且 TELEGRAM_BOT_TOKEN 存在时启动
    - 调用 getUpdates?offset=<offset>&timeout=30 长轮询
    - 每条 update 处理后推进 offset，避免重复消费
    - 非文字消息静默忽略
    - 网络异常时等待 2 秒后重试，不中断循环
    """
    if not _token():
        print("[channel/telegram] 跳过 polling：TELEGRAM_BOT_TOKEN 未设置")
        return

    if not _polling_enabled():
        print("[channel/telegram] 跳过 polling：TELEGRAM_POLLING_ENABLED 未设为 true")
        return

    print("Telegram polling started")

    async with httpx.AsyncClient() as client:
        # ── 启动时快速同步一次 offset，跳过积压消息，宣告"我是新主" ──
        try:
            resp = await client.get(
                _url("getUpdates"),
                params={"timeout": 0},
                timeout=5,
            )
            updates = resp.json().get("result", [])
            offset = updates[-1]["update_id"] + 1 if updates else 0
            print(
                f"[channel/telegram] startup offset={offset}（跳过 {len(updates)} 条积压消息）"
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[channel/telegram] 初始化 offset 失败（继续）: {e}")
            offset = 0

        # ── 主循环：超时 5s，cancel 最慢 5s 内响应 ──
        while True:
            try:
                resp = await client.get(
                    _url("getUpdates"),
                    params={"offset": offset, "timeout": 5},
                    timeout=7,  # 略大于 Telegram timeout
                )
                resp.raise_for_status()
                updates = resp.json().get("result", [])

                for upd in updates:
                    offset = upd["update_id"] + 1

                    msg = upd.get("message") or {}
                    text = msg.get("text")
                    chat_id = (msg.get("chat") or {}).get("id")

                    if text and chat_id is not None:
                        asyncio.create_task(on_message(chat_id, text))

            except asyncio.CancelledError:
                raise  # 让 lifespan 的 cancel 正常传播
            except Exception as e:
                print(f"[channel/telegram] polling error: {e}")
                await asyncio.sleep(2)
