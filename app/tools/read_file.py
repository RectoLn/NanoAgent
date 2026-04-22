from registry import tool
from tools.workspace import safe_path


@tool(
    name="read",
    description="读取指定路径的文本文件内容并返回。参数为文件路径（绝对路径或相对路径）。只能访问 workspace 目录。",
)
def read_file(file_path: str) -> str:
    if not file_path:
        return "错误：未提供文件路径"
    try:
        abs_path = safe_path(file_path)
    except PermissionError as e:
        return f"错误：{e}"
    if not abs_path.is_file():
        return f"错误：文件不存在或不是普通文件: {abs_path}"
    try:
        content = abs_path.read_text(encoding="utf-8")
        if len(content) > 5000:
            return content[:5000] + "\n...（文件过长，已截断）"
        return content
    except Exception as e:
        return f"读取文件失败: {e}"
