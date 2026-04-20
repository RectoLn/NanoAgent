from datetime import datetime

from registry import tool


@tool(
    name="get_current_time",
    description="获取当前本地时间（YYYY-MM-DD HH:MM:SS 格式），无需输入参数。",
)
def get_current_time(_: str = "") -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
