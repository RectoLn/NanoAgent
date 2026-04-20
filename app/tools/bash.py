import subprocess

from registry import tool


# 超时时间（秒）：防止命令卡死
_TIMEOUT = 30

# 输出截断上限（字符）：防止大输出撑爆 Prompt
_MAX_OUTPUT = 4000


@tool(
    name="bash",
    description=(
        "在当前容器中执行一条 bash 命令，返回 stdout + stderr 合并后的输出。"
        "参数为完整的 bash 命令字符串，例如：ls -la /app/workspace。"
        "命令会以 /bin/bash -c 方式执行；超时 30 秒；输出超 4000 字符会被截断。"
    ),
)
def bash(command: str = "") -> str:
    if not command or not command.strip():
        return "错误：命令为空，请提供要执行的 bash 命令"

    try:
        result = subprocess.run(
            ["/bin/bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return f"错误：命令执行超过 {_TIMEOUT} 秒，已被终止"
    except Exception as e:
        return f"错误：命令执行异常: {e}"

    stdout = result.stdout or ""
    stderr = result.stderr or ""
    code = result.returncode

    output_parts = [f"[exit code] {code}"]
    if stdout:
        output_parts.append(f"[stdout]\n{stdout}")
    if stderr:
        output_parts.append(f"[stderr]\n{stderr}")

    output = "\n".join(output_parts)

    if len(output) > _MAX_OUTPUT:
        output = output[:_MAX_OUTPUT] + f"\n...（输出过长，已截断，总长 {len(output)} 字符）"

    return output
