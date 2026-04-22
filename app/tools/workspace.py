"""
workspace.py — Agent 文件沙箱工具

提供两个常量和一个路径校验函数，供 read_file / write_file / edit_file 共用。

WORKSPACE_DIR   app/workspace/ 的绝对路径
TEMPLATES_DIR   app/templates/ 的绝对路径
safe_path(path) 将传入路径解析为绝对路径，若不在 WORKSPACE_DIR 内则抛出 PermissionError
"""

from pathlib import Path

# 本文件位于 app/tools/workspace.py，因此：
#   .parent       → app/tools/
#   .parent.parent → app/
_APP_DIR = Path(__file__).resolve().parent.parent

WORKSPACE_DIR: Path = (_APP_DIR / "workspace").resolve()
TEMPLATES_DIR: Path = (_APP_DIR / "templates").resolve()


def safe_path(path: str) -> Path:
    """
    将 path 解析为绝对路径并校验是否在 WORKSPACE_DIR 内。

    - 相对路径按进程 CWD 解析（与 os.path.abspath 一致）
    - 绝对路径直接使用
    - '../' 等逃逸路径全部拒绝

    Returns: 合法的绝对 Path 对象
    Raises:  PermissionError — 路径超出 workspace 范围
    """
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(WORKSPACE_DIR)
    except ValueError:
        raise PermissionError(
            f"拒绝访问：'{path}' 超出 workspace 目录范围 ({WORKSPACE_DIR})"
        )
    return resolved
