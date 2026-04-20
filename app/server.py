"""
FastAPI 服务：暴露 ToolCallAgent 为 HTTP 接口。

端点：
  POST /chat         阻塞式，一次返回完整结果
  GET  /chat/stream  SSE 流式，推送每步的工具调用/结果/最终答案
  GET  /             返回静态前端页面
  GET  /health       健康检查

SSE 事件类型：
  question        用户问题
  tool_call       模型发起工具调用  {name, input_preview, call_id}
  observation     工具执行结果      {content, call_id}
  todo_update     todo 列表快照     {items}
  answer_chunk    最终答案流式token {content}
  final           最终答案完整文本  {content}
  error           错误             {content}
  done            结束
"""

import json
import os
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from client import HelloAgentsLLM
from agent import ReActAgent
import tools  # noqa: F401 触发工具自动注册

# --- FastAPI 应用 ---
app = FastAPI(title="ReAct Agent API", version="0.1")

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
    provider: str = "kilo"  # 默认 kilo
    model_id: str = ""  # 空字符串时用默认模型


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
        # 默认 kilo
        api_key = os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_BASE_URL")
        model = model_id or os.getenv("LLM_MODEL_ID")

    if not all([api_key, base_url, model]):
        raise ValueError(f"Provider '{provider}' 配置不完整，请检查环境变量")

    return {"api_key": api_key, "base_url": base_url, "model": model}


def _new_agent(provider: str = "kilo", model_id: str = "") -> ReActAgent:
    """每次请求新建 Agent 实例（无状态）。"""
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
    return JSONResponse({"msg": "前端页面未找到，请访问 /docs 查看 API"}, status_code=404)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/todo")
def get_todo():
    """返回当前全局 Todo 列表快照。"""
    from todo_manager import TODO
    return {"items": TODO.items}


@app.get("/meta")
def meta(provider: str = Query("kilo", description="模型提供商"), model_id: str = Query("", description="模型 ID")):
    """返回当前配置元信息，供前端展示状态栏。"""
    try:
        config = _get_llm_config(provider, model_id)
        model_name = config["model"]
    except ValueError as e:
        model_name = f"⚠️ {e}"
    ctx_len = int(os.getenv("LLM_CTX_LEN", "32768"))
    return {
        "model_id": model_name,
        "ctx_len": ctx_len,
    }


@app.post("/chat")
def chat(req: ChatRequest):
    """
    阻塞式对话：调用 agent.run，一次返回完整结果。
    """
    if not req.question or not req.question.strip():
        return JSONResponse({"error": "question 不能为空"}, status_code=400)

    agent = _new_agent(req.provider, req.model_id)
    try:
        answer = agent.run(req.question)
    except Exception as e:
        return JSONResponse({"error": f"Agent 执行失败: {e}"}, status_code=500)

    return {"question": req.question, "answer": answer}


@app.get("/chat/stream")
def chat_stream(
    question: str = Query(..., description="用户问题"),
    provider: str = Query("kilo", description="模型提供商"),
    model_id: str = Query("", description="模型 ID"),
):
    """
    流式对话（Server-Sent Events）：
    每一步的 Thought / Action / Observation 作为独立事件推送给前端。

    前端用 EventSource 订阅本端点即可。
    """
    if not question or not question.strip():
        return JSONResponse({"error": "question 不能为空"}, status_code=400)

    agent = _new_agent(provider, model_id)

    def event_gen():
        try:
            for event in agent.run_iter(question):
                payload = json.dumps(event, ensure_ascii=False)
                # SSE 协议：每条消息以 "data: ...\n\n" 结尾
                yield f"data: {payload}\n\n"
        except Exception as e:
            err = json.dumps({"type": "error", "content": str(e)}, ensure_ascii=False)
            yield f"data: {err}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
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
