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

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, Path as FPath
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from client import HelloAgentsLLM
from agent import ReActAgent
from session_manager import SESSION_MGR
from task_manager import TASK_MGR
import tools  # noqa: F401 触发工具自动注册

# --- FastAPI 应用 ---
app = FastAPI(title="ReAct Agent API", version="0.2")

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


def _new_agent(provider: str = "kilo", model_id: str = "") -> ReActAgent:
    """每次请求新建 Agent 实例。"""
    config = _get_llm_config(provider, model_id)
    llm = HelloAgentsLLM(**config)
    return ReActAgent(llm=llm)


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


@app.get("/todo")
def get_todo():
    """返回当前全局 Todo 列表快照。"""
    from todo_manager import TODO

    return {"items": TODO.items}


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


# ───────────────────── 对话端点 ─────────────────────


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
    task = TASK_MGR.get_task(task_id)
    if not task:
        return JSONResponse({"error": "任务不存在"}, status_code=404)

    def event_gen():
        current_index = last_index
        while True:
            # 获取新事件
            new_events = TASK_MGR.get_events_from_index(task_id, current_index)
            for event in new_events:
                payload = json.dumps(event, ensure_ascii=False)
                yield f"data: {payload}\n\n"
                current_index += 1

            # 如果任务完成，退出
            if TASK_MGR.is_task_done(task_id):
                break

            # 短暂等待，避免忙等
            import time

            time.sleep(0.1)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ───────────────────── 对话端点 ─────────────────────


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
        # 首先推送 session_id 和 task_id 给前端
        yield f"data: {json.dumps({'type': 'session_id', 'session_id': session.session_id}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'task_id', 'task_id': task_id}, ensure_ascii=False)}\n\n"

        last_index = 0
        while True:
            # 获取新事件
            new_events = TASK_MGR.get_events_from_index(task_id, last_index)
            for event in new_events:
                if event["type"] == "new_messages":
                    # 保存本轮新消息到 session（不推给前端）
                    for msg in event["messages"]:
                        session.add_message(msg)
                    continue
                elif event["type"] == "todo_update":
                    # 更新 session.tasks
                    session.tasks = event["items"]
                payload = json.dumps(event, ensure_ascii=False)
                yield f"data: {payload}\n\n"
                last_index += 1

            # 如果任务完成，退出
            if TASK_MGR.is_task_done(task_id):
                break

            # 短暂等待，避免忙等
            import time

            time.sleep(0.1)

        # 任务完成后保存 session
        SESSION_MGR._save_session(session.session_id)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=9090,
        reload=False,
        log_level="info",
    )
