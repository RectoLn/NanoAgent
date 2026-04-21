"""
FastAPI 服务：暴露 ToolCallAgent 为 HTTP 接口。

端点：
  POST /chat                   阻塞式，一次返回完整结果
  GET  /chat/stream            SSE 流式，推送每步的工具调用/结果/最终答案
  GET  /                       返回静态前端页面
  GET  /health                 健康检查

  # 会话管理
  GET  /sessions               列出所有会话摘要
  POST /sessions               新建会话，返回 session_id
  GET  /sessions/{sid}         获取会话完整历史
  DELETE /sessions/{sid}       删除会话

SSE 事件类型：
  question        用户问题
  tool_call       模型发起工具调用  {name, input_preview, call_id}
  observation     工具执行结果      {content, call_id}
  todo_update     todo 列表快照     {items}
  answer_chunk    最终答案流式token {content}
  final           最终答案完整文本  {content}
  session_id      当前会话ID        {session_id}
  error           错误             {content}
  done            结束
"""

import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

# 确保无论从项目根目录还是 app/ 目录启动，本包内的模块都能正常导入
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import BackgroundTasks, FastAPI, Query, Path as FPath
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv, find_dotenv

# usecwd=True：从进程工作目录（项目根）向上搜索 .env，
# 避免 app/.env（空文件）被优先命中而遮蔽根目录的 .env
load_dotenv(find_dotenv(usecwd=True))

from client import HelloAgentsLLM
from agent import ToolCallAgent
from session_manager import SESSION_MGR, Session
from task_manager import TASK_MGR
from channel.telegram import send_message as tg_send, start_polling
import tools  # noqa: F401 触发工具自动注册


# --- lifespan：服务启动时开启 Telegram Long Polling ---


@asynccontextmanager
async def lifespan(app):
    async def _on_tg_message(chat_id: int, text: str):
        await run_and_reply(chat_id, f"tg_{chat_id}", text)

    asyncio.create_task(start_polling(_on_tg_message))
    yield


# --- FastAPI 应用 ---
app = FastAPI(title="ReAct Agent API", version="0.3", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件
_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# --- 数据模型 ---
class ChatRequest(BaseModel):
    question: str
    provider: str = "kilo"
    model_id: str = ""
    session_id: Optional[str] = None  # 若提供，则续接已有会话


class NewSessionRequest(BaseModel):
    provider: str = "kilo"
    model_id: str = ""


# --- 工具函数 ---
def load_system_prompt() -> str:
    """加载 system prompt 模板并注入 SOUL.md 和 USER.md 内容。"""
    prompt_path = Path(__file__).parent / "prompts" / "system.md"
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_template = f.read().strip()

    soul_path = Path(__file__).parent / "workspace" / "wiki" / "SOUL.md"
    if soul_path.exists():
        with open(soul_path, "r", encoding="utf-8") as f:
            soul = f.read().strip()
    else:
        soul = "名字：未设定"

    user_memory_path = Path(__file__).parent / "workspace" / "wiki" / "USER.md"
    if user_memory_path.exists():
        with open(user_memory_path, "r", encoding="utf-8") as f:
            user_memory = f.read().strip()
    else:
        user_memory = "暂无用户信息"

    return prompt_template.replace("{soul}", soul).replace("{user_memory}", user_memory)


def _get_llm_config(provider: str, model_id: str = "") -> dict:
    """根据 provider 返回对应的 LLM 配置。"""
    if provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        base_url = "https://api.deepseek.com"
        model = model_id or "deepseek-chat"
    elif provider == "kilo":
        api_key = os.getenv("KILO_API_KEY", os.getenv("LLM_API_KEY"))
        base_url = os.getenv("KILO_BASE_URL", os.getenv("LLM_BASE_URL"))
        model = model_id or os.getenv("KILO_MODEL_ID", os.getenv("LLM_MODEL_ID"))
    else:
        api_key = os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_BASE_URL")
        model = model_id or os.getenv("LLM_MODEL_ID")

    if not all([api_key, base_url, model]):
        raise ValueError(f"Provider '{provider}' 配置不完整，请检查环境变量")

    return {"api_key": api_key, "base_url": base_url, "model": model}


def _new_agent(provider: str = "kilo", model_id: str = "") -> ToolCallAgent:
    """每次请求新建 Agent 实例。"""
    config = _get_llm_config(provider, model_id)
    llm = HelloAgentsLLM(**config)
    agent = ToolCallAgent(llm=llm)
    agent.system_prompt = load_system_prompt()
    return agent


# --- 路由 ---
@app.get("/")
def index():
    """返回 Vue 前端页面。"""
    index_file = _STATIC_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(str(index_file))
    return JSONResponse(
        {"msg": "前端页面未找到，请访问 /docs 查看 API"}, status_code=404
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/meta")
def meta(provider: str = Query("kilo"), model_id: str = Query("")):
    """返回当前配置元信息，供前端展示状态栏。"""
    try:
        config = _get_llm_config(provider, model_id)
        model_name = config["model"]
    except ValueError as e:
        model_name = f"⚠️ {e}"
    ctx_len = int(os.getenv("LLM_CTX_LEN", "32768"))
    return {"model_id": model_name, "ctx_len": ctx_len}


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _sse_payload(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _poll_task_events(task_id: str, start_index: int = 0):
    """
    公共 SSE 生成器：从 start_index 开始轮询任务事件并推送给前端。
    跳过 new_messages（已在后台线程持久化）。
    客户端断开时（GeneratorExit）静默退出，后台任务继续运行。
    """
    index = start_index
    try:
        while True:
            for event in TASK_MGR.get_events_from_index(task_id, index):
                index += 1
                if event["type"] == "new_messages":
                    continue
                yield _sse_payload(event)
            if TASK_MGR.is_task_done(task_id):
                break
            time.sleep(0.05)
    except GeneratorExit:
        pass


# ───────────────────── 会话管理端点 ─────────────────────


@app.get("/sessions")
def list_sessions():
    """列出所有会话摘要（倒序）。"""
    return {"sessions": SESSION_MGR.list_sessions()}


@app.post("/sessions")
def create_session(req: NewSessionRequest):
    """显式新建空会话，返回 session_id。"""
    agent = _new_agent(req.provider, req.model_id)
    session = SESSION_MGR.create(system_prompt=agent.system_prompt)
    return {"session_id": session.session_id, "title": session.title}


@app.get("/sessions/{session_id}")
def get_session(session_id: str = FPath(...)):
    """获取指定会话的完整消息历史。"""
    session = SESSION_MGR.get(session_id)
    if not session:
        return JSONResponse({"error": "会话不存在"}, status_code=404)
    return session.history_to_dict()


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str = FPath(...)):
    """删除指定会话。"""
    ok = SESSION_MGR.delete(session_id)
    if not ok:
        return JSONResponse({"error": "会话不存在"}, status_code=404)
    return {"ok": True}


@app.get("/tasks/{task_id}/stream")
def task_stream(
    task_id: str = FPath(...),
    last_index: int = Query(0, description="已推送的事件索引，从此开始回放"),
):
    """
    任务观察流（Server-Sent Events）。
    纯观察接口，只回放历史事件和订阅新事件，不启动新任务。
    前端断开重连时使用此接口。
    """
    if not TASK_MGR.get_task(task_id):
        return JSONResponse({"error": "任务不存在"}, status_code=404)

    return StreamingResponse(
        _poll_task_events(task_id, start_index=last_index),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@app.post("/chat")
def chat(req: ChatRequest):
    """
    阻塞式对话：调用 agent.run，一次返回完整结果。
    支持 session_id 续接多轮对话。
    """
    if not req.question or not req.question.strip():
        return JSONResponse({"error": "question 不能为空"}, status_code=400)

    agent = _new_agent(req.provider, req.model_id)

    # 会话：获取或新建
    session = SESSION_MGR.get_or_create(
        req.session_id, system_prompt=agent.system_prompt
    )
    history = session.get_messages_for_llm()

    try:
        new_msgs: list = []
        final_answer = ""
        for event in agent.run_iter(req.question, history=history):
            if event["type"] == "final":
                final_answer = event["content"]
            elif event["type"] == "new_messages":
                new_msgs = event["messages"]
    except Exception as e:
        return JSONResponse({"error": f"Agent 执行失败: {e}"}, status_code=500)

    # 保存本轮新消息到 session
    for msg in new_msgs:
        session.add_message(msg)

    # 保存 session 到文件
    SESSION_MGR._save_session(session.session_id)

    return {
        "session_id": session.session_id,
        "question": req.question,
        "answer": final_answer,
    }


@app.get("/chat/stream")
def chat_stream(
    question: str = Query(..., description="用户问题"),
    provider: str = Query("kilo"),
    model_id: str = Query(""),
    session_id: str = Query("", description="会话ID，为空则新建会话"),
):
    """
    流式对话（Server-Sent Events）。
    支持 session_id 续接多轮对话；若为空则自动新建会话。

    前端用 EventSource 订阅本端点即可。
    """
    if not question or not question.strip():
        return JSONResponse({"error": "question 不能为空"}, status_code=400)

    agent = _new_agent(provider, model_id)

    # 会话：获取或新建
    sid = session_id.strip() or None
    session = SESSION_MGR.get_or_create(sid, system_prompt=agent.system_prompt)
    history = session.get_messages_for_llm()

    # 启动任务
    task_id = TASK_MGR.start_task(session.session_id, question, agent, history)

    def event_gen():
        # 推送 session_id 和 task_id 给前端，然后复用公共轮询生成器
        yield _sse_payload({"type": "session_id", "session_id": session.session_id})
        yield _sse_payload({"type": "task_id", "task_id": task_id})
        yield from _poll_task_events(task_id)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# ───────────────────── Telegram Webhook ─────────────────────


def extract_final_reply(task) -> str:
    """
    从 task.events 倒序查找最后一条 type=="final" 的事件，返回其 content。

    注意：agent.py 产出的事件格式中没有 type=="text" / role=="assistant" 的事件；
    最终答案对应的是 type=="final"。若找不到则返回默认提示。
    """
    for event in reversed(task.events):
        if event.get("type") == "final":
            return event.get("content", "")
    return "✅ 完成，但没有文字输出"


def _get_tg_session(session_id: str, system_prompt: str) -> Session:
    """
    按指定 session_id 获取或创建 Telegram 会话。

    SESSION_MGR.get_or_create() 在 session 不存在时会用随机 UUID 新建，
    导致 tg_{chat_id} 永远无法复用。此函数直接以 session_id 为 key 注册，
    确保同一用户每次都能续接同一条会话历史。
    """
    session = SESSION_MGR.get(session_id)
    if session is None:
        session = Session(session_id, system_prompt)
        SESSION_MGR._sessions[session_id] = session
        SESSION_MGR._save_session(session_id)
    return session


async def run_and_reply(chat_id: int, session_id: str, text: str) -> None:
    """后台协程：调用 Agent 处理消息并将结果发送给 Telegram 用户。"""
    # 1. 发送"处理中"提示
    await tg_send(chat_id, "⏳ 处理中...")

    # 2. 获取/创建 session，构造 agent
    agent = _new_agent()
    session = _get_tg_session(session_id, system_prompt=agent.system_prompt)
    history = session.get_messages_for_llm()

    # 3. 启动后台任务（在独立线程运行 agent）
    task_id = TASK_MGR.start_task(session_id, text, agent, history)

    # 4. 轮询直到任务完成
    while not TASK_MGR.is_task_done(task_id):
        await asyncio.sleep(1)

    # 5. 提取最终回复
    task = TASK_MGR.get_task(task_id)
    reply = extract_final_reply(task)

    # 6. 发送回复
    await tg_send(chat_id, reply)


@app.post("/webhook/telegram")
async def webhook_telegram(update: dict, background_tasks: BackgroundTasks):
    """
    接收 Telegram Webhook 推送。
    非文字消息直接忽略；文字消息在后台调用 Agent 并回复结果。
    """
    message = update.get("message", {})
    text = message.get("text")
    chat_id = message.get("chat", {}).get("id")

    # 非文字消息忽略
    if not text or not chat_id:
        return {"ok": True}

    session_id = f"tg_{chat_id}"
    background_tasks.add_task(run_and_reply, chat_id, session_id, text)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=9090,
        reload=False,
        log_level="info",
    )
