import asyncio
import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional

import registry
from agent import ToolCallAgent
from app.llm.client import LLMClient
from app.prompt_loader import load_prompt
from registry import tool
from todo_manager import TodoManager


_SUBAGENT_TIMEOUT = 600
_BATCH_TIMEOUT = 600
_SUB_SYSTEM_PROMPT = load_prompt("subagent_system.md")
_SUMMARY_PROMPT = load_prompt("subagent_summary.md")
_SUMMARY_FORMAT = """

输出格式必须使用 Markdown 二级标题，并且只使用以下标题：
## 结论
## 产出物
## 关键发现
## 未完成项
"""


def _degraded(err: object) -> str:
    return f"[子任务执行失败: {err}。请检查 wiki 获取已写入的产出物。]"


def _fallback_summary(reason: str) -> str:
    return (
        f"## 结论\n{reason}\n\n"
        "## 产出物\n请检查 wiki。\n\n"
        "## 关键发现\n无可用摘要。\n\n"
        "## 未完成项\n摘要未能正常生成。"
    )


def _build_sub_tools() -> Dict:
    return {
        name: executor
        for name, executor in registry.TOOL_EXECUTORS.items()
        if name != "run_subagent"
    }


def _emit_step(
    event_queue: Optional["queue.Queue"],
    call_id: str,
    step: int,
    tool: str,
    input_preview: str,
    observation_preview: str,
    sub_call_id: str = None,
    phase: str = "tool_result",
    running: bool = False,
    parent_call_id: str = None,
    task_id: str = None,
    task_title: str = None,
) -> None:
    if event_queue is None:
        return
    ev = {
        "type": "subagent_step",
        "call_id": call_id,
        "step": step,
        "tool": tool,
        "input_preview": input_preview,
        "observation_preview": observation_preview,
        "phase": phase,
        "running": running,
        "done": False,
    }
    if sub_call_id:
        ev["sub_call_id"] = sub_call_id
    if parent_call_id:
        ev["parent_call_id"] = parent_call_id
    if task_id:
        ev["task_id"] = task_id
    if task_title:
        ev["task_title"] = task_title
    event_queue.put(ev)


def _emit_task_start(
    event_queue: Optional["queue.Queue"],
    call_id: str,
    parent_call_id: str = None,
    task_id: str = None,
    task_title: str = None,
) -> None:
    if event_queue is None:
        return
    ev = {
        "type": "subagent_step",
        "call_id": call_id,
        "phase": "task_start",
        "done": False,
    }
    if parent_call_id:
        ev["parent_call_id"] = parent_call_id
    if task_id:
        ev["task_id"] = task_id
    if task_title:
        ev["task_title"] = task_title
    event_queue.put(ev)


def _emit_done(
    event_queue: Optional["queue.Queue"],
    call_id: str,
    summary: str,
    parent_call_id: str = None,
    task_id: str = None,
    task_title: str = None,
) -> None:
    if event_queue is None:
        return
    ev = {
        "type": "subagent_step",
        "call_id": call_id,
        "phase": "task_done",
        "done": True,
        "summary": summary,
    }
    if parent_call_id:
        ev["parent_call_id"] = parent_call_id
    if task_id:
        ev["task_id"] = task_id
    if task_title:
        ev["task_title"] = task_title
    event_queue.put(ev)


async def _summarize(llm, messages, task) -> str:
    try:
        summary_messages = list(messages) + [
            {
                "role": "user",
                "content": f"子任务：{task}\n\n{_SUMMARY_PROMPT}{_SUMMARY_FORMAT}",
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
        return _fallback_summary("子任务已执行，但摘要模型返回空内容。")
    except Exception as e:
        return _degraded(e)


async def _run_subagent_async(
    task,
    context,
    event_queue: Optional["queue.Queue"],
    call_id: str,
    parent_provider: str,
    parent_model_id: str,
    parent_call_id: str = None,
    task_id: str = None,
    task_title: str = None,
) -> str:
    parent_override = {
        key: value
        for key, value in {
            "provider": parent_provider,
            "model_id": parent_model_id,
        }.items()
        if value
    }
    llm = LLMClient(purpose="subagent", override=parent_override or None)
    agent = ToolCallAgent(
        llm=llm,
        todo=TodoManager(),
        tools_override=_build_sub_tools(),
        system_prompt=_SUB_SYSTEM_PROMPT,
    )
    question = f"子任务：{task}"
    if context:
        question += f"\n\n必要背景：{context}"

    pending_tool = {}
    step = 0
    for event in agent.run_iter(question):
        event_type = event.get("type")
        if event_type == "tool_call":
            step += 1
            sub_call_id = event.get("call_id")
            pending_tool[event.get("call_id")] = {
                "step": step,
                "tool": event.get("name", "unknown"),
                "input_preview": event.get("input_preview", ""),
            }
            _emit_step(
                event_queue,
                call_id,
                step,
                str(event.get("name", "unknown")),
                str(event.get("input_preview", "")),
                "",
                sub_call_id=sub_call_id,
                phase="tool_start",
                running=True,
                parent_call_id=parent_call_id,
                task_id=task_id,
                task_title=task_title,
            )
        elif event_type == "observation":
            sub_call_id = event.get("call_id")
            tool_info = pending_tool.pop(sub_call_id, {})
            observation = str(event.get("content", ""))
            _emit_step(
                event_queue,
                call_id,
                int(tool_info.get("step") or step + 1),
                str(tool_info.get("tool") or "unknown"),
                str(tool_info.get("input_preview") or ""),
                observation[:120] + ("…" if len(observation) > 120 else ""),
                sub_call_id=sub_call_id,
                phase="tool_result",
                running=False,
                parent_call_id=parent_call_id,
                task_id=task_id,
                task_title=task_title,
            )
    return await _summarize(llm, agent.messages, task)


def _run_one_core(
    task: str,
    context: str,
    event_queue: Optional["queue.Queue"],
    call_id: str,
    parent_provider: str,
    parent_model_id: str,
    parent_call_id: str = None,
    task_id: str = None,
    task_title: str = None,
) -> str:
    """Pure synchronous execution of one subagent. Returns summary string.
    Does NOT emit any done event. Timeout per subagent: _SUBAGENT_TIMEOUT."""
    result = {"value": ""}
    _emit_task_start(
        event_queue,
        call_id,
        parent_call_id=parent_call_id,
        task_id=task_id,
        task_title=task_title,
    )

    def target() -> None:
        try:
            result["value"] = asyncio.run(
                _run_subagent_async(
                    task, context, event_queue, call_id,
                    parent_provider, parent_model_id,
                    parent_call_id=parent_call_id,
                    task_id=task_id,
                    task_title=task_title,
                )
            )
        except Exception as e:
            result["value"] = _degraded(e)

    thread = threading.Thread(target=target, name="nanoagent-subagent-core")
    thread.start()
    thread.join(timeout=_SUBAGENT_TIMEOUT)
    if thread.is_alive():
        return f"[子任务超时（>{_SUBAGENT_TIMEOUT}s），已中止。请检查 wiki 获取已写入的产出物。]"
    return result["value"] or _degraded("empty result")


def _run_single(
    task: str,
    context: str,
    event_queue: Optional["queue.Queue"],
    call_id: str,
    parent_provider: str,
    parent_model_id: str,
) -> str:
    """Single-task wrapper: execute one subagent and emit parent done."""
    summary = _run_one_core(
        task, context, event_queue, call_id,
        parent_provider, parent_model_id,
    )
    _emit_done(event_queue, call_id, summary)
    return summary


def _format_batch_summary(tasks: list, results: dict) -> str:
    success_count = sum(
        1 for r in results.values()
        if "超时" not in r and "失败" not in r and "异常" not in r
    )
    lines = [
        "## 结论",
        f"批量子任务完成: {success_count}/{len(tasks)} 成功。",
        "",
        "## 产出物",
    ]
    for t in tasks:
        tid = t.get("id", "?")
        ok = tid in results and "超时" not in results[tid] and "失败" not in results[tid] and "异常" not in results[tid]
        lines.append(f"- {'✅' if ok else '❌'} **{tid}**: {t.get('task', '')[:100]}")
    lines.append("")
    lines.append("## 关键发现")
    lines.append("详见各子任务输出。以下为各子任务摘要：")
    lines.append("")
    for tid, result in results.items():
        lines.append(f"### {tid}")
        lines.append(result[:500])
        lines.append("")
    lines.append("## 未完成项")
    unfinished = [
        (tid, r) for tid, r in results.items()
        if "超时" in r or "失败" in r or "异常" in r
    ]
    if unfinished:
        for tid, r in unfinished:
            lines.append(f"- {tid}: {r[:150]}")
    else:
        lines.append("- 无")
    return "\n".join(lines)


def _run_batch(
    tasks: list,
    max_concurrency: int,
    event_queue: Optional["queue.Queue"],
    parent_call_id: str,
    parent_provider: str,
    parent_model_id: str,
    batch_timeout: int = _BATCH_TIMEOUT,
) -> str:
    results: Dict[str, str] = {}
    futures_map: Dict = {}
    task_by_id = {}

    max_workers = max(1, int(max_concurrency or 1))

    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        for t in tasks:
            if not isinstance(t, dict):
                t = {"id": str(len(task_by_id) + 1), "task": str(t)}
            tid = str(t.get("id", ""))
            if not tid:
                tid = str(len(task_by_id) + 1)
            task_by_id[tid] = t
            child_call_id = f"{parent_call_id}/{tid}"
            future = executor.submit(
                _run_one_core,
                str(t.get("task", "")),
                str(t.get("context", "")),
                event_queue,
                child_call_id,
                parent_provider,
                parent_model_id,
                parent_call_id=parent_call_id,
                task_id=tid,
                task_title=str(t.get("task", ""))[:120],
            )
            futures_map[future] = tid

        try:
            for future in as_completed(futures_map, timeout=batch_timeout):
                tid = futures_map[future]
                try:
                    summary = future.result(timeout=0)
                except Exception as e:
                    summary = _fallback_summary(f"子任务执行异常: {e}")
                results[tid] = summary
                task = task_by_id.get(tid, {})
                _emit_done(
                    event_queue, f"{parent_call_id}/{tid}", summary,
                    parent_call_id=parent_call_id, task_id=tid,
                    task_title=str(task.get("task", tid))[:120],
                )
        except TimeoutError:
            pass

        for future, tid in futures_map.items():
            if tid not in results:
                fallback = _fallback_summary(f"子任务未在 {batch_timeout}s 内完成")
                results[tid] = fallback
                task = task_by_id.get(tid, {})
                _emit_done(
                    event_queue, f"{parent_call_id}/{tid}", fallback,
                    parent_call_id=parent_call_id, task_id=tid,
                    task_title=str(task.get("task", tid))[:120],
                )
    finally:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            # Python 3.8 does not support cancel_futures.
            executor.shutdown(wait=False)

    summary = _format_batch_summary(tasks, results)
    _emit_done(event_queue, parent_call_id, summary)
    return summary


@tool(
    name="run_subagent",
    description=(
        "派发子任务给独立 Agent 执行，隔离上下文避免污染父任务。"
        "支持单任务（task 为字符串）或批量并发（task 为对象数组）。"
        "子 Agent 拥有除 run_subagent 外的所有工具。"
        "执行完成后消息历史丢弃，只返回结构化摘要。"
    ),
)
def run_subagent(
    task,
    context: str = "",
    event_queue: Optional["queue.Queue"] = None,
    call_id: str = "",
    parent_provider: str = "",
    parent_model_id: str = "",
    max_concurrency: int = 3,
) -> str:
    """
    派发子任务给独立 Agent 执行。

    Args:
        task: 单任务描述字符串，或批量任务对象数组 [{id, task, context?}]。
        context: 父任务必要背景（单任务模式）。批量模式在每个对象中单独指定。
        max_concurrency: 批量模式下的最大并发子 Agent 数，默认 3。

    Returns:
        结构化摘要：结论 + 产出物 + 关键发现 + 未完成项
    """
    if isinstance(task, list):
        return _run_batch(
            task, max_concurrency, event_queue, call_id,
            parent_provider, parent_model_id, batch_timeout=_BATCH_TIMEOUT,
        )
    return _run_single(
        str(task or ""), str(context or ""), event_queue, call_id,
        parent_provider, parent_model_id,
    )
