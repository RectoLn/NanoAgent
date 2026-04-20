import os

from registry import tool


@tool(
    name="read",
    description="读取指定路径的文本文件内容并返回。参数为文件路径（绝对路径或相对路径）。",
)
def read_file(file_path: str) -> str:
    if not file_path:
        return "错误：未提供文件路径"
    abs_path = os.path.abspath(file_path)
    if not os.path.isfile(abs_path):
        return f"错误：文件不存在或不是普通文件: {abs_path}"
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        if len(content) > 5000:
            return content[:5000] + "\n...（文件过长，已截断）"
        return content
    except Exception as e:
        return f"读取文件失败: {e}"
