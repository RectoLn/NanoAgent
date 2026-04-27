"""
compact 工具：Agent 主动触发上下文压缩（Layer 3）。

工具本身不直接执行压缩逻辑（压缩需要访问 messages 和 LLM，工具函数
无法直接操作）。它返回一个特殊标记字符串，agent.py 的 run_iter() 
检测到 tool_name == "compact" 时拦截并执行真正的 auto_compact 流程。
"""

COMPACT_SENTINEL = "__COMPACT__"


def compact() -> str:
    """
    触发上下文压缩。agent.py 检测到此返回值后执行 auto_compact。
    工具函数本身不做任何事，仅作为触发信号。
    """
    return COMPACT_SENTINEL
