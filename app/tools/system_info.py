import platform
import sys

from registry import tool


@tool(
    name="get_system_info",
    description="获取当前容器的操作系统版本与 Python 版本，无需输入参数。",
)
def get_system_info(_: str = "") -> str:
    os_name = platform.system()
    os_release = platform.release()
    os_version = platform.version()
    python_version = sys.version.split()[0]
    machine = platform.machine()
    return (
        f"操作系统: {os_name} {os_release} ({os_version}); "
        f"架构: {machine}; "
        f"Python 版本: {python_version}"
    )
