import asyncio
import threading
from typing import Dict

import registry
from agent import ToolCallAgent
from app.llm.client import LLMClient
from app.prompt_loader import load_prompt
from registry import tool
from todo_manager import TodoManager


_SUB_SYSTEM_PROMPT = load_prompt("subagent_system.md")
_SUMMARY_PROMPT = load_prompt("subagent_summary.md")


def _degraded(err: object) -> str:
    return f"[子任务执行失败: {err}。请检查 wiki 获取已写入的产出物。]"


def _build_sub_tools() -> Dict:
    return {
        name: executor
        for name, executor in registry.TOOL_EXECUTORS.items()
        if name != "run_subagent"
    }


async def _summarize(llm, messages, task) -> str:
    try:
        summary_messages = list(messages) + [
            {
                "role": "user",
                "content": f"子任务：{task}\n\n{_SUMMARY_PROMPT}",
            }
        ]
        response = llm.call(
            messages=summary_messages,
            tools=None,
            temperature=0.1,
            max_tokens=800,
        )
        summary = ((response.content if response else "") or "").strip()
        if summary:
            return summary
        return "结论：子任务已执行，但摘要模型返回空内容。\n产出物：请检查 wiki。\n关键发现：无可用摘要。\n未完成项：摘要生成为空。"
    except Exception as e:
        return _degraded(e)


async def _run_subagent_async(task, context) -> str:
    llm = LLMClient()
    agent = ToolCallAgent(
        llm=llm,
        todo=TodoManager(),
        tools_override=_build_sub_tools(),
        system_prompt=_SUB_SYSTEM_PROMPT,
    )
    question = f"子任务：{task}"
    if context:
        question += f"\n\n必要背景：{context}"

    agent.run(question)
    return await _summarize(llm, agent.messages, task)


def _run_in_thread(task, context) -> str:
    result = {"value": ""}

    def target() -> None:
        try:
            result["value"] = asyncio.run(_run_subagent_async(task, context))
        except Exception as e:
            result["value"] = _degraded(e)

    thread = threading.Thread(target=target, name="nanoagent-subagent")
    thread.start()
    thread.join()
    return result["value"] or _degraded("empty result")


@tool(
    name="run_subagent",
    description=(
        "派发子任务给独立 Agent 执行，隔离上下文避免污染父任务。"
        "子 Agent 拥有除 run_subagent 外的所有工具。"
        "执行完成后消息历史丢弃，只返回结构化摘要。"
    ),
)
def run_subagent(task: str, context: str = "") -> str:
    """
    派发子任务给独立 Agent 执行，隔离上下文避免污染父任务。
    子 Agent 拥有除 run_subagent 外的所有工具。
    执行完成后消息历史丢弃，只返回结构化摘要。

    Args:
        task: 子任务描述。需说明：做什么、预期产出格式、产出物应写入的 wiki 路径。
        context: 父任务必要背景，精简传递，禁止粘贴完整对话历史。

    Returns:
        结构化摘要：结论 + 产出物路径 + 关键发现 + 未完成项
    """
    return _run_in_thread(task, context or "")


registry.TOOL_EXECUTORS["run_subagent"] = run_subagent

if not any(
    (schema.get("function") or {}).get("name") == "run_subagent"
    for schema in registry.TOOLS_SCHEMA
):
    registry.TOOLS_SCHEMA.append(
        {
            "type": "function",
            "function": {
                "name": "run_subagent",
                "description": (
                    "派发子任务给独立 Agent 执行，隔离上下文避免污染父任务。"
                    "执行完成后只返回结构化摘要。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": (
                                "子任务描述。需说明做什么、预期产出格式、"
                                "产出物应写入的 wiki 路径。"
                            ),
                        },
                        "context": {
                            "type": "string",
                            "description": "父任务必要背景，精简传递，禁止粘贴完整对话历史。",
                        },
                    },
                    "required": ["task"],
                },
            },
        }
    )
