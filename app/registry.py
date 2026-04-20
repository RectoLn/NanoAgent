"""
全局工具注册表 + @tool 装饰器。

使用方式：
    from registry import tool

    @tool(name="xxx", description="...")
    def my_tool(input_str: str) -> str:
        ...

所有用 @tool 装饰的函数会自动进入全局 TOOLS 表，
无需手动在 main.py 里 register。
"""

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
    """生成供 Prompt 使用的工具说明清单。"""
    if not TOOLS:
        return "（无可用工具）"
    return "\n".join(f"- {n}: {m['description']}" for n, m in TOOLS.items())


def execute(tool_name: str, tool_input: str = "") -> str:
    """执行工具；失败返回错误字符串。"""
    if tool_name not in TOOLS:
        return f"错误：未找到名为 '{tool_name}' 的工具。可用工具：{get_tool_names()}"
    try:
        func = TOOLS[tool_name]["func"]
        result = func(tool_input) if tool_input else func()
        return str(result)
    except Exception as e:
        return f"工具 '{tool_name}' 执行失败: {e}"
