# NanoAgent v0.3 - 项目进度总结

## 项目概述

NanoAgent 是一个基于 ReAct 模式的轻量级 AI Agent 实现，采用 FastAPI 后端 + Vue 3 前端，支持多模型 LLM 调用、工具系统、任务管理和会话持久化。

## 代码结构

```
app/
├── agent.py              # Tool Call 主循环实现
├── client.py             # LLM 客户端（OpenAI 兼容接口）
├── registry.py           # 工具注册表（自动扫描 tools/ 目录）
├── session_manager.py    # 会话持久化管理（文件夹存储）
├── todo_manager.py       # 全局 Todo 状态管理（单例）
├── server.py             # FastAPI 服务端点
├── config.yaml           # 配置参数（max_steps, temperature 等）
├── prompts/system.md     # 系统提示模板
├── tools/                # 工具实现目录
│   ├── bash.py          # Bash 命令执行
│   ├── edit_file.py     # 文件编辑
│   ├── read_file.py     # 文件读取
│   ├── web_fetch.py     # 网页抓取
│   ├── write_file.py    # 文件写入
│   └── todo.py          # Todo 管理
├── static/               # 前端资源
│   └── index.html       # Vue 3 单页应用
└── workspace/           # 工作区（.gitignore 忽略）
    ├── test.txt         # 测试文件
    ├── wiki/            # 文档目录
    └── project/         # 示例项目（已忽略）
```

## 已实现功能

### ✅ 核心功能
- **Tool Call 循环**：基于 OpenAI Tool Call 协议的原生工具调用
- **多模型支持**：DeepSeek (V3 Chat / R1 Reasoner)、Kilo (GPT-4o / Claude 3.5 等)
- **工具系统**：@tool 装饰器自动注册，支持动态工具扩展
- **Web UI**：FastAPI SSE 流式输出 + Vue 3 响应式前端
- **实时流式**：逐 token 实时渲染，支持中断恢复

### ✅ 会话管理 (P0 - 已完成)
- **多轮对话**：上下文传递，支持连续对话
- **会话持久化**：每个 session 独立 JSON 文件存储
- **会话切换**：前端支持创建/删除/切换会话
- **自动恢复**：页面刷新后恢复上次会话

### ✅ 任务管理 (Todo)
- **多步骤规划**：Agent 自动分解复杂任务
- **进度跟踪**：实时更新任务状态（pending/in_progress/completed/cancelled）
- **视觉反馈**：右侧面板显示任务进度条和状态
- **会话绑定**：任务状态与当前会话持久化关联
- **独立运行**：任务在后端独立线程执行，支持前端断开重连
- **中断恢复**：切换会话/刷新不影响任务执行，前端可重新观察

### ✅ 用户体验优化
- **响应式布局**：支持桌面/移动端，三栏自适应
- **中断恢复**：loading 时可切换会话，自动中断当前流，支持任务重连
- **错误处理**：网络错误、模型异常的友好提示
- **面板折叠**：左侧会话列表和右侧任务面板支持折叠

### ✅ 部署支持
- **Docker 化**：Dockerfile + docker-compose.yml 一键部署
- **跨平台**：Linux/macOS/Windows Docker Desktop 支持
- **环境配置**：.env 文件配置 API Key，支持多提供商

## 待实现功能

### 🔄 短期优化 (P0 - 核心基础)
1. **会话管理** ← *地基，没它其他都跑不起来（正在进度中）*
   - ✅ 已完成：基础会话持久化、切换、删除
   - 🔄 待完善：多用户隔离、会话权限控制

2. **消息平台对接** ← *简历最大亮点，让agent"活"起来*
   - 🔄 计划：集成微信/钉钉/飞书等消息平台
   - 目标：Agent 可以通过消息平台接收任务并响应

### 🔄 中期规划 (P1 - 技术深度)
3. **LLM Wiki** ← *技术深度，面试聊得起来*
   - 🔄 计划：构建 Agent 知识库和文档系统
   - 目标：支持 Agent 从 Wiki 中检索信息和学习

4. **Multi-agent** ← *最高技术含量，压轴*
   - 🔄 计划：实现多 Agent 协作架构
   - 目标：Agent 间任务分配、通信和协调

### 🔄 长期愿景 (P2 - 高级特性)
5. **上下文压缩** ← *做了前四个自然需要它*
   - 🔄 计划：长对话上下文压缩和摘要
   - 目标：突破 LLM token 限制，支持超长对话

6. **定时任务** ← *锦上添花*
   - 🔄 计划：Agent 定时执行任务
   - 目标：支持 cron-like 任务调度

7. **心跳检测** ← *最后做，生产级细节*
   - 🔄 计划：Agent 健康监控和自动重启
   - 目标：生产环境稳定性保证

## 全局重要脚本、函数、变量

### 🔧 核心类和函数

#### SessionManager (session_manager.py)
- `SessionManager()`: 单例，管理所有会话
- `_save_session(session_id)`: 保存单个会话到 JSON
- `_load()`: 启动时加载所有会话文件
- `create(system_prompt)`: 新建会话
- `get(session_id)`: 获取会话
- `get_or_create(session_id, system_prompt)`: 获取或创建
- `delete(session_id)`: 删除会话

#### TaskManager (task_manager.py)
- `TaskManager()`: 单例，管理所有后台任务
- `start_task(session_id, question, agent, history)`: 启动后台任务，返回 task_id
- `get_task(task_id)`: 获取任务状态
- `get_events_from_index(task_id, last_index)`: 获取新事件用于回放
- `is_task_done(task_id)`: 检查任务是否完成

#### ToolCallAgent (agent.py)
- `ToolCallAgent(llm)`: 初始化 Agent
- `run_iter(question, history=None)`: 核心 Tool Call 循环生成器
- `run(question)`: 阻塞式执行

#### FastAPI 端点 (server.py)
- `GET /`: 返回前端页面
- `GET /chat/stream`: SSE 流式对话（启动后台任务）
- `GET /tasks/{task_id}/stream`: SSE 任务观察流（纯观察接口）
- `POST /chat`: 阻塞式对话
- `GET /sessions`: 列出会话摘要
- `POST /sessions`: 新建会话
- `GET /sessions/{sid}`: 获取会话详情
- `DELETE /sessions/{sid}`: 删除会话

### 📊 重要变量

#### 环境变量 (.env)
- `LLM_API_KEY`: Kilo API Key
- `LLM_BASE_URL`: Kilo Gateway URL
- `LLM_MODEL_ID`: 默认模型 ID
- `DEEPSEEK_API_KEY`: DeepSeek API Key

#### 全局状态
- `SESSION_MGR`: SessionManager 单例
- `TASK_MGR`: TaskManager 单例 (task_manager.py)
- `TODO`: TodoManager 单例 (todo_manager.py)
- `TOOLS_SCHEMA`: 工具描述列表 (registry.py)

#### 前端状态 (static/index.html)
- `timeline`: 当前会话消息数组
- `todos`: 当前任务列表
- `sessions`: 会话摘要列表
- `currentSessionId`: 当前会话 ID
- `currentTaskId`: 当前任务 ID
- `currentEventSource`: 当前活跃的 EventSource

### 🛠️ 配置参数 (config.yaml)
```yaml
agent:
  max_steps: 30          # 最大推理步骤
  temperature: 0.1       # LLM 温度参数

prompts:
  system: prompts/system.md  # 系统提示文件路径
```

### 📝 工具注册模式 (registry.py)
```python
TOOL_REGISTRY = {}
def tool(func):
    TOOL_REGISTRY[func.__name__] = func
    return func

def execute_tool_call(name, args_json):
    # 调用工具函数
```

## 开发环境

- **Python**: 3.8+
- **依赖**: fastapi, uvicorn, openai, pyyaml, python-dotenv
- **前端**: Vue 3 + Marked.js
- **部署**: Docker + docker-compose

## 更新日志

### v0.2 (当前 - 2026-04-20)
- ✅ 重构 SessionManager 为文件夹存储
- ✅ 添加会话持久化和多轮对话
- ✅ 优化前端 UX：面板折叠、中断恢复
- ✅ 完善 Todo 会话绑定和持久化
- ✅ Docker Desktop Windows 支持
- ✅ 项目进度文档化
- ✅ 实现任务独立运行和重连机制

### 下一步开发规划 (按优先级)
1. 会话管理完善（多用户隔离）
2. 消息平台对接（微信/钉钉集成）
3. LLM Wiki 系统
4. Multi-agent 架构
5. 上下文压缩
6. 定时任务系统
7. 心跳检测与监控

### v0.1
- ✅ 基础 Tool Call 实现
- ✅ Web UI 和流式输出
- ✅ 工具系统和 Todo 管理
- ✅ 多模型支持

---

*最后更新: 2026-04-20*