"""
Session Manager：持久化会话管理器

每个会话维护：
  - session_id: 唯一标识符
  - title: 会话标题（首条用户消息的前20字）
  - messages: 标准 OpenAI 格式消息列表（含 system/user/assistant/tool）
  - tasks: 任务列表
  - created_at: 创建时间
  - updated_at: 最后更新时间

消息格式（OpenAI标准）：
  {"role": "system",    "content": "..."}
  {"role": "user",      "content": "..."}
  {"role": "assistant", "content": "...", "tool_calls": [...]}
  {"role": "tool",      "tool_call_id": "...", "content": "..."}
"""

import uuid
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


class Session:
    def __init__(self, session_id: str, system_prompt: str = ""):
        self.session_id = session_id
        self.title = "新对话"
        self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
        # messages 不含 system，system 单独存储
        self.system_prompt = system_prompt
        self.messages: List[Dict[str, Any]] = []
        self.tasks: List[Dict[str, Any]] = []
        # 上下文压缩历史，每条压缩操作追加一条记录
        self.compression_history: List[Dict[str, Any]] = []

    def add_message(self, msg: Dict[str, Any]):
        """追加一条消息到历史。"""
        self.messages.append(msg)
        self.updated_at = datetime.now().isoformat()
        # 以第一条用户消息的前20字作为标题
        if self.title == "新对话" and msg.get("role") == "user":
            content = msg.get("content", "") or ""
            self.title = content[:30] + ("…" if len(content) > 30 else "")

    def get_messages_for_llm(self) -> List[Dict[str, Any]]:
        """返回供 LLM 使用的完整消息列表（含 system）。"""
        result = []
        if self.system_prompt:
            result.append({"role": "system", "content": self.system_prompt})
        result.extend(self.messages)
        return result

    def to_dict(self) -> Dict[str, Any]:
        """序列化为前端可用的字典。"""
        return {
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": len(self.messages),
        }

    def history_to_dict(self) -> Dict[str, Any]:
        """返回含完整消息历史和任务的字典。"""
        return {
            **self.to_dict(),
            "messages": self.messages,
            "tasks": self.tasks,
        }

    def should_compress(
        self,
        token_threshold: int = 6000,
        message_threshold: int = 30,
    ) -> bool:
        """
        判断是否需要压缩上下文。
        - 消息数超过 message_threshold，或
        - 估算 token 数超过 token_threshold
        注：token 用空格分词粗估，实际 token 数偏低，留出余地。
        """
        if len(self.messages) > message_threshold:
            return True
        token_count = sum(
            len((msg.get("content") or "").split()) for msg in self.messages
        )
        return token_count > token_threshold

    def add_compression_record(self, record: Dict[str, Any]) -> None:
        """追加一条压缩记录，字段由调用方提供。"""
        self.compression_history.append(record)
        self.updated_at = datetime.now().isoformat()

    def get_compression_candidates(self, keep_recent: int = 10) -> List[Dict]:
        """
        返回可压缩的消息段（保留最近 keep_recent 条，压缩其余部分）。
        若消息总数不足，返回空列表表示无需压缩。
        """
        if len(self.messages) <= keep_recent + 5:
            return []
        return self.messages[:-keep_recent]


class SessionManager:
    """持久化会话管理器（保存到 sessions/ 文件夹）。"""

    def __init__(self):
        self._dir = Path(__file__).parent / "sessions"
        self._dir.mkdir(exist_ok=True)
        self._sessions: Dict[str, Session] = {}
        self._load()

    def _save_session(self, session_id: str):
        """保存单个 session 到文件。"""
        if session_id not in self._sessions:
            return
        s = self._sessions[session_id]
        data = {
            "session_id": s.session_id,
            "title": s.title,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
            "system_prompt": s.system_prompt,
            "messages": s.messages,
            "tasks": s.tasks,
            "compression_history": s.compression_history,
        }
        file_path = self._dir / f"{session_id}.json"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存 session {session_id} 失败: {e}")

    def _load(self):
        """扫描 sessions/ 文件夹加载所有 sessions。"""
        for file_path in self._dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                sid = d["session_id"]
                s = Session(sid, d.get("system_prompt", ""))
                s.title = d.get("title", "新对话")
                s.created_at = d.get("created_at", datetime.now().isoformat())
                s.updated_at = d.get("updated_at", datetime.now().isoformat())
                s.messages = d.get("messages", [])
                s.tasks = d.get("tasks", [])
                s.compression_history = d.get("compression_history", [])
                self._sessions[sid] = s
            except Exception as e:
                print(f"加载 session {file_path.name} 失败: {e}")

    def create(self, system_prompt: str = "") -> Session:
        """创建新会话，返回 Session 对象。"""
        sid = str(uuid.uuid4())
        session = Session(sid, system_prompt)
        self._sessions[sid] = session
        self._save_session(sid)
        return session

    def get(self, session_id: str) -> Optional[Session]:
        """按 ID 获取会话，不存在返回 None。"""
        return self._sessions.get(session_id)

    def get_or_create(
        self, session_id: Optional[str], system_prompt: str = ""
    ) -> Session:
        """若 session_id 存在则取出，否则新建。"""
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        return self.create(system_prompt)

    def delete(self, session_id: str) -> bool:
        """删除会话，返回是否成功。"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            file_path = self._dir / f"{session_id}.json"
            if file_path.exists():
                file_path.unlink()
            return True
        return False

    def list_sessions(self) -> List[Dict[str, Any]]:
        """返回所有会话的摘要列表，按更新时间倒序。"""
        sessions = [s.to_dict() for s in self._sessions.values()]
        sessions.sort(key=lambda x: x["updated_at"], reverse=True)
        return sessions

    def update_session(self, session_id: str):
        """标记 session 更新并保存。"""
        if session_id in self._sessions:
            self._sessions[session_id].updated_at = datetime.now().isoformat()
            self._save_session(session_id)


# 全局单例
SESSION_MGR = SessionManager()
