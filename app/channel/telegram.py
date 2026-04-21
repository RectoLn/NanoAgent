"""
Telegram Bot 通道封装（Long Polling 主模式，Webhook 备用）。

本地测试（无需 ngrok）：
1. 在 .env 中配置：
       TELEGRAM_BOT_TOKEN=你的BotToken

2. 启动服务：
       uvicorn app.server:app --port 8000

3. 观察日志出现：
       Telegram polling started

4. 打开 Telegram，向 Bot 发任意文字消息。
   Bot 会先回复 "⏳ 处理中..."，Agent 处理完成后回复最终结果。
"""

import asyncio
import os
from typing import Awaitable, Callable

import httpx

_API = "https://api.telegram.org/bot{token}/{method}"
_MAX_MSG_LEN = 4096


def _token() -> str | None:
    """延迟读取，避免模块加载时 .env 尚未完全注入。"""
    return os.getenv("TELEGRAM_BOT_TOKEN")


def _url(method: str) -> str:
    return _API.format(token=_token(), method=method)


async def send_message(chat_id: int | str, text: str) -> None:
    """
    向指定 chat_id 发送文字消息。
    - parse_mode="Markdown"
    - 超过 4096 字符自动分段发送
    """
    if not _token():
        print(f"[channel/telegram] 无法发送消息（Token 未设置）: {text[:80]}")
        return

    chunks = [
        text[i : i + _MAX_MSG_LEN] for i in range(0, len(text), _MAX_MSG_LEN)
    ] or [""]

    async with httpx.AsyncClient() as client:
        for chunk in chunks:
            # 先尝试 Markdown，失败（通常是内容含不合法 MD 字符）则降级纯文本
            for parse_mode in ("Markdown", None):
                payload = {"chat_id": chat_id, "text": chunk}
                if parse_mode:
                    payload["parse_mode"] = parse_mode
                try:
                    resp = await client.post(
                        _url("sendMessage"), json=payload, timeout=10
                    )
                    resp.raise_for_status()
                    break  # 成功，不需要降级
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 400 and parse_mode:
                        # Markdown 解析失败，降级到纯文本重试
                        continue
                    print(f"[channel/telegram] 发送消息失败: {e}")
                    break
                except Exception as e:
                    print(f"[channel/telegram] 发送消息失败: {e}")
                    break


async def start_polling(
    on_message: Callable[[int, str], Awaitable[None]],
) -> None:
    """
    Long Polling 主循环。

    参数：
        on_message(chat_id, text) — 收到文字消息时的回调协程

    行为：
    - 调用 getUpdates?offset=<offset>&timeout=30 长轮询
    - 每条 update 处理后推进 offset，避免重复消费
    - 非文字消息静默忽略
    - 网络异常时等待 2 秒后重试，不中断循环
    """
    if not _token():
        print("[channel/telegram] 跳过 polling：TELEGRAM_BOT_TOKEN 未设置")
        return

    print("Telegram polling started")

    offset = 0
    async with httpx.AsyncClient() as client:
        while True:
            try:
                resp = await client.get(
                    _url("getUpdates"),
                    params={"offset": offset, "timeout": 30},
                    timeout=35,  # 比 Telegram timeout 略大，避免过早超时
                )
                resp.raise_for_status()
                updates = resp.json().get("result", [])

                for upd in updates:
                    # 无论消息是否处理，都推进 offset
                    offset = upd["update_id"] + 1

                    msg = upd.get("message") or {}
                    text = msg.get("text")
                    chat_id = (msg.get("chat") or {}).get("id")

                    if text and chat_id is not None:
                        # 每条消息独立创建 Task，互不阻塞
                        asyncio.create_task(on_message(chat_id, text))

            except Exception as e:
                print(f"[channel/telegram] polling error: {e}")
                await asyncio.sleep(2)
