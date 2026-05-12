import queue
import threading
from typing import Any, Dict, Generator, Optional


def run_subagent_with_events(
    subagent_args: Optional[Dict[str, Any]],
    parse_error: Optional[Exception],
    call_id: str,
    parent_provider: str,
    parent_model_id: str,
) -> Generator[Dict[str, Any], None, str]:
    """Run the subagent tool while forwarding its live events to the caller."""
    if parse_error:
        return f"错误：工具参数 JSON 解析失败: {parse_error}"

    from tools.subagent import run_subagent

    subagent_args = subagent_args or {}
    subagent_events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
    subagent_result = {"value": ""}

    task_arg = subagent_args.get("task") or ""
    context_arg = str(subagent_args.get("context") or "")
    max_conc = int(subagent_args.get("max_concurrency", 3))

    def run_subagent_tool() -> None:
        kwargs = {
            "event_queue": subagent_events,
            "call_id": call_id,
            "parent_provider": parent_provider,
            "parent_model_id": parent_model_id,
        }
        if isinstance(task_arg, list) or "max_concurrency" in subagent_args:
            kwargs["max_concurrency"] = max_conc
        subagent_result["value"] = run_subagent(
            task_arg,
            context_arg,
            **kwargs,
        )

    subagent_thread = threading.Thread(
        target=run_subagent_tool,
        name="nanoagent-run-subagent-tool",
        daemon=True,
    )
    subagent_thread.start()
    result = ""
    while True:
        try:
            ev = subagent_events.get(timeout=0.3)
            if ev.get("done") and ev.get("call_id") == call_id:
                result = ev.get("summary", "")
                break
            yield ev
        except queue.Empty:
            if not subagent_thread.is_alive():
                result = subagent_result.get("value", "")
                break
    subagent_thread.join(timeout=0)
    return result or subagent_result.get("value", "") or "错误：run_subagent 返回空结果"
