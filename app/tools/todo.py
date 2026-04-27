import json

from registry import tool, get_thread_local_todo


@tool(
    name="todo",
    description=(
        "管理多步任务的 todo 列表。整体替换当前列表。"
        "参数为 JSON 数组字符串，每项包含 id / text / status。"
        "status 取值：pending / in_progress / completed / cancelled。"
        "同一时间最多 1 个 in_progress（强制聚焦）。"
        "示例："
        '[{"id":"1","text":"读取 SOUL.md","status":"completed"},'
        '{"id":"2","text":"写入 test.txt","status":"in_progress"},'
        '{"id":"3","text":"汇报结果","status":"pending"}]'
    ),
)
def todo(raw_input: str = "") -> str:
    """
    内部实现已改为从线程局部读取 TodoManager 实例，
    通过 registry.get_thread_local_todo() 获取当前 Agent 的 TodoManager。
    不再依赖全局单例。
    """
    todo_manager = get_thread_local_todo()
    if todo_manager is None:
        return "错误：TodoManager 未初始化"
    
    if not raw_input or not raw_input.strip():
        # 空参数 → 返回当前状态（只读）
        return todo_manager.render()

    try:
        items = json.loads(raw_input)
    except json.JSONDecodeError as e:
        return f"错误：JSON 解析失败：{e}。参数应为 JSON 数组字符串。"

    return todo_manager.update(items)
