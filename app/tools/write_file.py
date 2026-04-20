import os

from registry import tool


@tool(
    name="write_file",
    description=(
        "写入或覆盖一个文本文件。"
        "参数格式为 '文件路径|||文件内容'（用三个竖线 ||| 作为分隔符）。"
        "例如：/app/workspace/note.md|||这是一段新内容。"
        "若文件已存在将被覆盖；父目录不存在时会自动创建。"
    ),
)
def write_file(raw_input: str) -> str:
    if not raw_input or "|||" not in raw_input:
        return "错误：参数格式应为 '文件路径|||文件内容'（使用 ||| 作为分隔符）"

    file_path, _, content = raw_input.partition("|||")
    file_path = file_path.strip()
    if not file_path:
        return "错误：文件路径为空"

    abs_path = os.path.abspath(file_path)

    # 自动创建父目录
    parent = os.path.dirname(abs_path)
    try:
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
    except Exception as e:
        return f"创建父目录失败: {e}"

    try:
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        # 统一放开权限，便于宿主机用户（如 VS Code）后续编辑
        try:
            os.chmod(abs_path, 0o777)
        except Exception as chmod_err:
            # chmod 失败不影响写入本身，仅提示
            print(f"[write_file] chmod 0o777 失败（忽略）: {chmod_err}")
        size = os.path.getsize(abs_path)
        return f"✅ 已写入 {abs_path}（{size} 字节，{len(content)} 字符，权限 0o777）"
    except Exception as e:
        return f"写入文件失败: {e}"
