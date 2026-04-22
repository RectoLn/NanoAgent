import os

from registry import tool
from tools.workspace import safe_path


# 与 write_file 保持一致的三竖线分隔符
_SEP = "|||"


@tool(
    name="edit",
    description=(
        "对已存在的文本文件做局部修改：查找 old_text 并替换为 new_text。"
        f"参数格式：'文件路径{_SEP}old_text{_SEP}new_text'（用三个竖线 ||| 分隔 3 段）。"
        "例如：workspace/main.py|||import os|||import sys"
        "如果要删除某段文本，new_text 留空即可，例如：workspace/a.txt|||要删除的片段|||"
        "要求 old_text 在文件中**恰好出现一次**，否则返回错误，以避免误改。只能访问 workspace 目录。"
    ),
)
def edit_file(raw_input: str) -> str:
    if not raw_input or raw_input.count(_SEP) < 2:
        return "错误：参数格式应为 '文件路径|||old_text|||new_text'（必须包含两个 ||| 分隔符）"

    # 用 split(sep, 2) 保证前两个 ||| 划分三段，
    # new_text 里即便再次出现 ||| 也不会被误切
    parts = raw_input.split(_SEP, 2)
    if len(parts) != 3:
        return "错误：参数格式应为 '文件路径|||old_text|||new_text'"

    file_path, old_text, new_text = parts
    file_path = file_path.strip()

    if not file_path:
        return "错误：文件路径为空"
    if not old_text:
        return "错误：old_text 不能为空（如需从头写入请使用 write_file）"

    try:
        abs_path = safe_path(file_path)
    except PermissionError as e:
        return f"错误：{e}"

    if not abs_path.is_file():
        return f"错误：文件不存在或不是普通文件: {abs_path}"

    # 读取原文件
    try:
        content = abs_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"读取文件失败: {e}"

    # 检查 old_text 出现次数：必须恰好 1 次，避免歧义误改
    occurrences = content.count(old_text)
    if occurrences == 0:
        return (
            f"错误：在 {abs_path} 中未找到 old_text。"
            "请先 read 文件确认确切字符（含空格/缩进/换行）后再调用 edit。"
        )
    if occurrences > 1:
        return (
            f"错误：old_text 在 {abs_path} 中出现了 {occurrences} 次，"
            "为避免误改请扩大 old_text 的上下文，使其全文唯一。"
        )

    # 执行替换并写回
    new_content = content.replace(old_text, new_text, 1)
    try:
        abs_path.write_text(new_content, encoding="utf-8")
        # 文件权限 666（宿主机可读写，不可执行）
        try:
            os.chmod(str(abs_path), 0o666)
        except Exception as chmod_err:
            print(f"[edit_file] chmod 0o666 失败（忽略）: {chmod_err}")
    except Exception as e:
        return f"写回文件失败: {e}"

    delta = len(new_content) - len(content)
    action = "删除" if new_text == "" else "替换"
    return (
        f"✅ 已对 {abs_path} 执行 {action}（old_text {len(old_text)} 字符 -> "
        f"new_text {len(new_text)} 字符，文件净变化 {delta:+d} 字符，权限 0o666）"
    )
