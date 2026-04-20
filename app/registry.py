"""
全局工具注册表 + @tool 装饰器 + Tool Call Schema。

工具函数用 @tool 装饰器注册，TOOLS_SCHEMA 用于传给 OpenAI-compatible API，
TOOL_EXECUTORS 用于 harness 执行工具调用。
"""

import json
from typing import Callable, Dict, Any, List

# 全局注册表：工具名 -> { description, func }
TOOLS: Dict[str, Dict[str, Any]] = {}


def tool(name: str, description: str) -> Callable:
    """装饰器：把函数注册为工具。"""
    def decorator(func: Callable) -> Callable:
        if name in TOOLS:
            print(f"⚠️ 工具 {name} 已存在，将被覆盖。")
        TOOLS[name] = {
            "description": description,
            "func": func,
        }
        return func
    return decorator


def get_tool_names() -> List[str]:
    return list(TOOLS.keys())


def get_tool_descriptions() -> str:
    """生成供 Prompt 使用的工具说明清单（兼容旧 ReAct 模式）。"""
    if not TOOLS:
        return "（无可用工具）"
    return "\n".join(f"- {n}: {m['description']}" for n, m in TOOLS.items())


def execute(tool_name: str, tool_input: str = "") -> str:
    """执行工具（旧 ReAct 文本模式，保留兼容）。"""
    if tool_name not in TOOLS:
        return f"错误：未找到名为 '{tool_name}' 的工具。可用工具：{get_tool_names()}"
    try:
        func = TOOLS[tool_name]["func"]
        result = func(tool_input) if tool_input else func()
        return str(result)
    except Exception as e:
        return f"工具 '{tool_name}' 执行失败: {e}"


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
    from todo_manager import TODO
    if tasks is None:
        return TODO.render()
    return TODO.update(tasks)


def _exec_get_current_time() -> str:
    from tools.current_time import get_current_time
    return get_current_time()


def _exec_get_system_info() -> str:
    from tools.system_info import get_system_info
    return get_system_info()


def _exec_web_fetch(url: str = "") -> str:
    from tools.web_fetch import web_fetch
    return web_fetch(url)


# 工具名 -> kwargs 执行函数
TOOL_EXECUTORS: Dict[str, Callable] = {
    "bash": _exec_bash,
    "read": _exec_read,
    "write_file": _exec_write_file,
    "edit": _exec_edit,
    "todo": _exec_todo,
    "get_current_time": _exec_get_current_time,
    "get_system_info": _exec_get_system_info,
    "web_fetch": _exec_web_fetch,
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
                        "description": "要执行的完整 bash 命令，例如 'ls -la /app/workspace'"
                    }
                },
                "required": ["command"]
            }
        }
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
                        "description": "文件的绝对路径或相对路径"
                    }
                },
                "required": ["path"]
            }
        }
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
                        "description": "文件路径（绝对路径或相对路径）"
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的完整文件内容"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "对已存在的文件做局部替换。old_str 必须在文件中恰好出现一次，否则报错。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径"
                    },
                    "old_str": {
                        "type": "string",
                        "description": "要被替换的原始字符串（必须在文件中唯一存在）"
                    },
                    "new_str": {
                        "type": "string",
                        "description": "替换后的新字符串，留空表示删除"
                    }
                },
                "required": ["path", "old_str", "new_str"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "todo",
            "description": "整体替换任务列表，同一时间最多 1 个 in_progress 任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "description": "完整的任务列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "text": {"type": "string"},
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed", "cancelled"]
                                }
                            },
                            "required": ["id", "text", "status"]
                        }
                    }
                },
                "required": ["tasks"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前本地时间（YYYY-MM-DD HH:MM:SS 格式），无需参数。",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "获取当前容器的操作系统版本与 Python 版本，无需参数。",
            "parameters": {"type": "object", "properties": {}}
        }
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
                        "description": "目标 URL，例如 'https://httpbin.org/get'"
                    }
                },
                "required": ["url"]
            }
        }
    },
]
