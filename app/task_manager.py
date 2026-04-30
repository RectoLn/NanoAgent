"""
Task Manager: 独立运行任务，支持断开重连观察。

TaskState:
- task_id: str
- session_id: str
- status: pending/running/done/error/cancelled
- events: list  # 所有已产生的 events，用于回放
- thread: Thread

TaskManager:
- 维护 task_id -> TaskState 字典
- start_task(): 在独立线程启动任务
"""

import threading
import uuid
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from agent import ToolCallAgent
from session_manager import SESSION_MGR


@dataclass
class TaskState:
    task_id: str
    session_id: str
    status: str = "pending"  # pending/running/done/error/cancelled
    cancel_requested: bool = False
    events: List[Dict[str, Any]] = field(default_factory=list)
    thread: Optional[threading.Thread] = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, TaskState] = {}

    def start_task(
        self,
        session_id: str,
        question: str,
        agent: ToolCallAgent,
        history: Optional[List[Dict]] = None,
    ) -> str:
        """启动新任务，在独立线程运行 agent.run_iter()，直接在线程内保存 session"""
        task_id = str(uuid.uuid4())
        task_state = TaskState(task_id=task_id, session_id=session_id, status="pending")
        self.tasks[task_id] = task_state

        session = SESSION_MGR.get(session_id)

        def should_cancel() -> bool:
            with task_state.lock:
                return task_state.cancel_requested

        def run_task():
            with task_state.lock:
                task_state.status = "running"

            try:
                for event in agent.run_iter(
                    question,
                    history=history,
                    should_cancel=should_cancel,
                ):
                    # 在线程内直接处理消息和 todo，与前端连接无关
                    if event["type"] == "message_delta" and session:
                        session.add_message(event["message"])
                        SESSION_MGR._save_session(session_id)
                    elif event["type"] == "context_snapshot" and session:
                        # Snapshot replaces prior deltas after compaction; keep this after message_delta handling.
                        session.replace_messages_from_llm(event["messages"])
                        SESSION_MGR._save_session(session_id)
                    elif event["type"] == "todo_update" and session:
                        session.tasks = event["items"]
                        SESSION_MGR._save_session(session_id)

                    with task_state.lock:
                        task_state.events.append(event)

                with task_state.lock:
                    if task_state.cancel_requested:
                        task_state.status = "cancelled"
                    else:
                        task_state.status = "done"

            except Exception as e:
                with task_state.lock:
                    task_state.status = "error"
                    task_state.events.append({"type": "error", "content": str(e)})
                    task_state.events.append({"type": "done"})
                if session:
                    SESSION_MGR._save_session(session_id)

        thread = threading.Thread(target=run_task, daemon=True)
        task_state.thread = thread
        thread.start()

        return task_id

    def get_task(self, task_id: str) -> Optional[TaskState]:
        """获取任务状态"""
        return self.tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """Request a task to stop after the current non-interruptible operation."""
        task = self.get_task(task_id)
        if not task:
            return False

        with task.lock:
            if task.status in ["done", "error", "cancelled"]:
                return True
            task.cancel_requested = True
            return True

    def get_events_from_index(
        self, task_id: str, last_index: int
    ) -> List[Dict[str, Any]]:
        """获取从 last_index 开始的新事件"""
        task = self.get_task(task_id)
        if not task:
            return []

        with task.lock:
            if last_index >= len(task.events):
                return []
            return task.events[last_index:]

    def is_task_done(self, task_id: str) -> bool:
        """检查任务是否完成"""
        task = self.get_task(task_id)
        if not task:
            return True
        with task.lock:
            return task.status in ["done", "error", "cancelled"]


# 全局 TaskManager 实例
TASK_MGR = TaskManager()
