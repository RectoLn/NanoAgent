"""
工具执行器 + Tool Call Schema。

TOOL_EXECUTORS: 工具名 -> kwargs 执行函数，供 execute_tool_call() 调用。
TOOLS_SCHEMA:   OpenAI-compatible API 的工具描述列表，传给 LLM。

tools/ 目录下各模块仍用 @tool 装饰器注册（供 tools/__init__.py 自动发现），
但注册结果（TOOLS 字典）不再使用，已移除。

ThreadLocal 线程局部存储：
- 每个 Agent 执行时通过 set_thread_local_todo() 注入自己的 TodoManager 实例
- 工具函数通过 get_thread_local_todo() 读取，避免全局单例的并发竞态
"""

import json
import threading
from typing import Callable, Dict, Any, List, Optional


# ─────────────────────────────────────────────
# Thread Local：每个 Agent 的 TodoManager 实例注入点
# ─────────────────────────────────────────────

_thread_local = threading.local()


def set_thread_local_todo(todo_manager, session=None) -> None:
    """设置当前线程的 TodoManager 实例和 Session（由 Agent.run_iter 调用）。"""
    _thread_local.todo = todo_manager
    _thread_local.session = session


def get_thread_local_todo():
    """获取当前线程的 TodoManager 实例（由 _exec_todo 调用）。"""
    return getattr(_thread_local, "todo", None)


def get_thread_local_session():
    """获取当前线程的 Session 实例（由 _exec_get_token_usage 调用）。"""
    return getattr(_thread_local, "session", None)


def tool(name: str, description: str) -> Callable:
    """装饰器：供 tools/ 各模块使用，保持文件结构不变；注册结果不再收集。"""

    def decorator(func: Callable) -> Callable:
        return func

    return decorator


# ─────────────────────────────────────────────
# Tool Call 模式：kwargs 适配器
# ─────────────────────────────────────────────


def _exec_bash(command: str = "") -> str:
    from tools.bash import bash

    return bash(command)


def _exec_read(path: str = "") -> str:
    from tools.read_file import read_file

    return read_file(path)


def _exec_write_file(path: str = "", content: str = "") -> str:
    from tools.write_file import write_file

    return write_file(f"{path}|||{content}")


def _exec_edit(path: str = "", old_str: str = "", new_str: str = "") -> str:
    from tools.edit_file import edit_file

    return edit_file(f"{path}|||{old_str}|||{new_str}")


def _exec_todo(tasks: list = None) -> str:
    """
    执行 todo 工具，读取当前线程的 TodoManager 实例。
    
    当 Agent 执行时，先通过 set_thread_local_todo() 注入自己的实例，
    然后在工具调用时这里读取，实现 per-agent 的 todo 隔离。
    """
    todo = get_thread_local_todo()
    if todo is None:
        return "错误：TodoManager 未初始化，请重新启动任务"
    
    if tasks is None:
        return todo.render()
    return todo.update(tasks)


def _exec_todo_add(text: str = "", id: str = "", status: str = "pending") -> str:
    todo = get_thread_local_todo()
    if todo is None:
        return "错误：TodoManager 未初始化，请重新启动任务"
    return todo.add_item(text=text, item_id=id or None, status=status)


def _exec_todo_update(id: str = "", status: str = "", text: str = "") -> str:
    todo = get_thread_local_todo()
    if todo is None:
        return "错误：TodoManager 未初始化，请重新启动任务"
    return todo.update_item(id, status=status or None, text=text or None)


def _exec_todo_replan(reason: str = "", tasks: list = None, items: list = None) -> str:
    todo = get_thread_local_todo()
    if todo is None:
        return "错误：TodoManager 未初始化，请重新启动任务"
    return todo.replan(tasks or items or [], reason=reason)


def _exec_get_current_time() -> str:
    from tools.current_time import get_current_time

    return get_current_time()


def _exec_get_system_info() -> str:
    from tools.system_info import get_system_info

    return get_system_info()


def _exec_web_fetch(url: str = "") -> str:
    from tools.web_fetch import web_fetch

    return web_fetch(url)


def _exec_install_skill(url: str = "") -> str:
    from tools.install_skill import install_skill

    return install_skill(url)


def _exec_compact() -> str:
    from tools.compact import compact

    return compact()


def _exec_get_token_usage() -> str:
    """获取当前会话的 token 使用统计。"""
    session = get_thread_local_session()
    if session is None:
        return "错误：Session 未初始化，无法获取 token 使用统计"

    usage = session.token_usage
    return f"""当前会话 Token 使用统计：
- 输入 Token（Prompt）: {usage['total_prompt_tokens']}
- 输出 Token（Completion）: {usage['total_completion_tokens']}
- 总 Token: {usage['total_tokens']}
"""


# 工具名 -> kwargs 执行函数
TOOL_EXECUTORS: Dict[str, Callable] = {
    "bash": _exec_bash,
    "read": _exec_read,
    "write_file": _exec_write_file,
    "edit": _exec_edit,
    "todo_add": _exec_todo_add,
    "todo_update": _exec_todo_update,
    "todo_replan": _exec_todo_replan,
    "todo": _exec_todo,
    "get_current_time": _exec_get_current_time,
    "get_system_info": _exec_get_system_info,
    "web_fetch": _exec_web_fetch,
    "install_skill": _exec_install_skill,
    "get_token_usage": _exec_get_token_usage,
}


def execute_tool_call(tool_name: str, arguments_json: str) -> str:
    """
    Tool Call 模式的执行入口。
    arguments_json: tool_call.function.arguments（JSON 字符串）
    """
    executor = TOOL_EXECUTORS.get(tool_name)
    if not executor:
        return f"错误：未知工具 '{tool_name}'，可用工具：{list(TOOL_EXECUTORS.keys())}"
    try:
        arguments = json.loads(arguments_json) if arguments_json.strip() else {}
    except json.JSONDecodeError as e:
        return f"错误：工具参数 JSON 解析失败: {e}"
    try:
        result = executor(**arguments)
        return str(result)
    except TypeError as e:
        return f"错误：工具 '{tool_name}' 参数不匹配: {e}"
    except Exception as e:
        return f"错误：工具 '{tool_name}' 执行失败: {type(e).__name__}: {e}"


# ─────────────────────────────────────────────
# Tool Call API JSON Schema
# ─────────────────────────────────────────────

TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "在容器中执行 bash 命令，返回 stdout + stderr。超时 30 秒，输出超 4000 字符自动截断。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的完整 bash 命令，例如 'ls -la /app/workspace'",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "读取本地文件内容，超过 5000 字符自动截断。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件的绝对路径或相对路径",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "将内容写入本地文件（覆盖写入）。父目录不存在时自动创建。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（绝对路径或相对路径）",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的完整文件内容",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "对已存在的文件做局部替换。old_str 必须在文件中恰好出现一次，否则报错。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "old_str": {
                        "type": "string",
                        "description": "要被替换的原始字符串（必须在文件中唯一存在）",
                    },
                    "new_str": {
                        "type": "string",
                        "description": "替换后的新字符串，留空表示删除",
                    },
                },
                "required": ["path", "old_str", "new_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_add",
            "description": "新增一条 Todo，不替换现有任务列表。适合追加子任务或创建初始计划中的单项任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "可选任务 ID；留空时自动生成。",
                    },
                    "text": {"type": "string", "description": "任务内容"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                        "description": "任务状态，默认 pending。",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_update",
            "description": "按 ID 更新单条 Todo 的状态或内容。完成一步、切换 in_progress 时使用它。",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "要更新的任务 ID"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                        "description": "可选，新状态。",
                    },
                    "text": {"type": "string", "description": "可选，新任务内容。"},
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_replan",
            "description": "显式重规划并替换完整 Todo 列表。必须提供 reason；只有原计划不再适用时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "为什么需要替换现有 Todo，不能留空。",
                    },
                    "tasks": {
                        "type": "array",
                        "description": "新的完整任务列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "text": {"type": "string"},
                                "status": {
                                    "type": "string",
                                    "enum": [
                                        "pending",
                                        "in_progress",
                                        "completed",
                                        "cancelled",
                                    ],
                                },
                            },
                            "required": ["id", "text", "status"],
                        },
                    },
                },
                "required": ["reason", "tasks"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前本地时间（YYYY-MM-DD HH:MM:SS 格式），无需参数。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "获取当前容器的操作系统版本与 Python 版本，无需参数。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": (
                "获取指定 URL 的网页内容。"
                "HTML 页面自动去除脚本/样式并提取纯文本；JSON/纯文本直接返回。"
                "结果截断至 8000 字符，超时 15 秒。仅支持 http/https。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "目标 URL，例如 'https://httpbin.org/get'",
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "install_skill",
            "description": "Install a Skill into workspace. Supports ClawHub URL/slug and GitHub repository or tree URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "ClawHub Skill URL/slug or GitHub URL, for example 'weather', 'https://clawhub.ai/steipete/weather', or 'https://github.com/owner/repo/tree/main/path/to/skill'",
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compact",
            "description": "当你感到上下文过长影响推理时，主动调用此工具压缩上下文。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_token_usage",
            "description": "获取当前会话的累积 Token 使用统计，包括输入 Token、输出 Token 和总 Token。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]
