# NanoAgent v0.6 - 项目进度总结

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
├── channel/              # 消息平台接入层
│   ├── __init__.py      # 包初始化
│   └── telegram.py      # Telegram Bot API 封装
├── tools/                # 工具实现目录
│   ├── bash.py          # Bash 命令执行
│   ├── edit_file.py     # 文件编辑
│   ├── read_file.py     # 文件读取
│   ├── web_fetch.py     # 网页抓取
│   ├── write_file.py    # 文件写入
│   ├── todo.py          # Todo 管理
│   └── workspace.py     # 安全沙箱（safe_path 路径校验）
├── static/               # 前端资源
│   └── index.html       # Vue 3 单页应用
├── templates/            # 初始模板（git 版本控制）
│   └── wiki/            # Wiki 初始化模板
│       ├── SOUL.md
│       ├── USER.md
│       ├── log.md
│       ├── index.md
│       ├── skills/
│       │   └── index.md
│       ├── concepts/
│       └── entities/
└── workspace/           # 工作区（运行时数据，.gitignore 忽略）
    ├── untracked/       # 原始资料（未加工）
    ├── ingested/        # 已摄取（中间态）
    └── wiki/            # Agent 知识库
        ├── concepts/    # 概念页
        ├── entities/   # 实体页
└── skills/     # 技能页
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

### ✅ Telegram Bot 接入
- **Long Polling**：服务启动即自动开始拉取消息，无需 ngrok 或公网地址
- **显式开关**：`TELEGRAM_POLLING_ENABLED=true` 才会启动 polling，防止多实例共享 token 时意外抢占
- **Webhook 备用**：`POST /webhook/telegram` 路由保留，可随时切换
- **独立会话**：每个 Telegram 用户独立 session（session_id = `tg_{chat_id}`）
- **异步处理**：每条消息独立 Task，互不阻塞
- **HTML 格式渲染**：LLM Markdown 自动转换为 Telegram HTML（支持代码块、粗体、斜体），降级为纯文本兜底
- **长消息分段**：超过 4096 字符自动分段发送

### ✅ LLM Wiki 三层架构 + Skill 技能积累
- **templates/ 目录**：初始模板由 git 版本控制，Agent 运行时只操作 workspace/
- **workspace/ 目录**：纯运行时数据，.gitignore 完全忽略
- **初始化流程**：首次启动时自动从 templates/ 复制文件到 workspace/
- **三层知识库**：
  - `concepts/`：概念页（抽象知识、原理）
  - `entities/`：实体页（具体实体、人物、项目）
  - `skills/`：技能页（任务执行经验）
- **Skill 机制**：满足条件时自动记录技能到 skills/，同步更新 skills/index.md

### ✅ 安全沙箱
- **safe_path()**：所有文件工具（read/write/edit）必须通过路径校验
- **路径逃逸防护**：`../` 等逃逸路径一律拒绝，仅允许 workspace/ 内操作
- **单例导入**：workspace.py 提供 WORKSPACE_DIR、TEMPLATES_DIR 常量

## 待实现功能

### 🔄 短期优化 (P0 - 核心基础)
1. **会话管理** 
   - ✅ 已完成：基础会话持久化、切换、删除
   - 🔄 待完善：多用户隔离、会话权限控制

2. **消息平台对接** 
   - ✅ 已完成：Telegram Bot 接入（Long Polling，无需公网）
   - 🔄 待扩展：微信/钉钉/飞书等消息平台

### 🔄 中期规划 (P1 - 技术深度)
1. **LLM Wiki** 
   - ✅ 已完成：三层架构（concepts/entities/skills） + Skill 积累机制
   - ✅ 已完成：templates/ git 版本控制 + workspace/ 运行时隔离
   - ✅ 已完成：安全沙箱（safe_path 路径校验）
   - 🔄 待完善：concepts/entities 自动分类优化

2. **Multi-agent** 
   - 🔄 计划：实现多 Agent 协作架构
   - 目标：Agent 间任务分配、通信和协调

### 🔄 长期愿景 (P2 - 高级特性)
1. **上下文压缩** 
   - 🔄 计划：长对话上下文压缩和摘要
   - 目标：突破 LLM token 限制，支持超长对话

2. **定时任务** 
   - 🔄 计划：Agent 定时执行任务
   - 目标：支持 cron-like 任务调度

3. **心跳检测** 
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
- `POST /webhook/telegram`: 接收 Telegram Webhook 推送（备用），非文字消息忽略，文字消息后台处理并回复

#### 公共辅助 (server.py)
- `_poll_task_events(task_id, start_index)`: SSE 事件轮询生成器，`chat_stream` 和 `task_stream` 共用
- `_sse_payload(event)`: 将 event dict 格式化为 SSE data 行
- `_SSE_HEADERS`: SSE 响应头常量
- `extract_final_reply(task)`: 从 TaskState.events 倒序查找最后一条 `type=="final"` 事件，返回其 content
- `run_and_reply(chat_id, session_id, text)`: 后台 async 协程，发"处理中"提示 → 调用 Agent → 发最终回复
- `_ensure_workspace_init()`: 服务启动时将 templates/ 复制到 workspace/（仅当目标不存在）

#### 安全沙箱 (tools/workspace.py)
- `WORKSPACE_DIR`: app/workspace/ 绝对路径
- `TEMPLATES_DIR`: app/templates/ 绝对路径
- `safe_path(path)`: 路径校验，不在 WORKSPACE_DIR 内则抛出 PermissionError

#### Telegram 封装 (channel/telegram.py)
- `send_message(chat_id, text)`: 异步发送 Telegram 消息，LLM Markdown → HTML 转换，降级纯文本兜底，超 4096 字符自动分段
- `start_polling(on_message)`: Long Polling 主循环，需 `TELEGRAM_POLLING_ENABLED=true` 才启动，`getUpdates(offset, timeout=30)` 长轮询
- `_md_to_html(text)`: LLM CommonMark → Telegram HTML 转换（代码块、行内代码、粗体、斜体）
- `_polling_enabled()`: 检测 `TELEGRAM_POLLING_ENABLED` 环境变量

#### 前端公共函数 (static/index.html)
- `attachStreamHandlers(es, opts)`: 统一绑定 SSE `onmessage`/`onerror`，`send` 和 `resumeTask` 共用

### 📊 重要变量

#### 环境变量 (.env)
- `LLM_API_KEY`: Kilo API Key
- `LLM_BASE_URL`: Kilo Gateway URL
- `LLM_MODEL_ID`: 默认模型 ID
- `DEEPSEEK_API_KEY`: DeepSeek API Key
- `TELEGRAM_BOT_TOKEN`: Telegram Bot Token（由 @BotFather 获取，可选）
- `TELEGRAM_POLLING_ENABLED`: 设为 `true` 才启动 Long Polling（默认 false，防多实例抢占）

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

### v0.8 (2026-04-24)

**Telegram 渲染修复（MarkdownV2 三级降级）**
- `channel/telegram.py`：重写消息格式化，采用 Telegram MarkdownV2 作为首选格式，支持标题、表格（转等宽代码块）、列表、粗体、斜体、行内代码、围栏代码块
- 新增 `_escape_v2`、`_escape_code_v2`、`_process_inline_v2`、`_md_to_markdownv2`、`_md_to_html_simple` 五个辅助函数
- `send_message` 实现三级降级链：MarkdownV2 → HTML → 纯文本，每级失败（400）时打日志并自动尝试下一级
- 表格处理：先剥离行内格式（**bold**、*italic*、\`code\`），再放入等宽代码块，避免内部出现转义字符
- 围栏代码块：不携带语言标识（如 ```python），防止 Telegram 解析异常（`</>` 图标）
- `.env.example`：保留 `TELEGRAM_POLLING_ENABLED=false` 说明

### v0.7 (2026-04-24)

**Telegram 稳定性修复**
- `channel/telegram.py`：新增 `TELEGRAM_POLLING_ENABLED=true` 显式开关，token 存在但未开启时静默跳过，防止多实例（9090/9091）共享 token 互相抢占 updates
- `channel/telegram.py`：新增 `_md_to_html()` 转换函数，将 LLM CommonMark 输出转为 Telegram HTML（围栏代码块、行内代码、`**bold**`、`*italic*`），`send_message` 改用 HTML 模式发送，400 时降级纯文本
- `.env.example`：新增 `TELEGRAM_POLLING_ENABLED=false` 字段说明

### v0.6 (2026-04-24)

**ClawHub Skill 系统优化**
- 整理技能目录结构：将 `workspace/SKILL.md` 移动到 `workspace/skills/weather/SKILL.md`，区分技能定义与使用经验
- 新增 `templates/skills/.gitkeep`：确保新项目初始化后 `workspace/skills/` 目录存在
- 更新 `server.py` `_ensure_workspace_init()`：启动时自动创建 `workspace/skills/` 目录
- 新增 `tools/install_skill.py`：自动化安装 ClawHub Skill 的工具函数，实现从 URL 下载、解压、依赖检查、文档创建、索引更新
- 更新 `registry.py`：添加 `install_skill` 工具注册，支持 Tool Call 调用
- 更新 `prompts/system.md`：新增 ClawHub Skill 安装协议，Agent 收到 ClawHub URL 时自动调用 `install_skill` 工具
- 确认 `safe_path()` 白名单：`workspace/skills/` 在允许路径内

**Wiki 维护规范更新**
- 目录职责明确：`skills/{name}/SKILL.md` 为只读技能定义，`wiki/skills/{name}.md` 为可更新使用经验

### v0.5 (2026-04-22)

**LLM Wiki 三层架构 + Skill 技能积累**
- `templates/` 目录：初始模板由 git 版本控制，与运行时隔离
- `workspace/` 目录：纯运行时数据，.gitignore 完全忽略
- `tools/workspace.py`：新增 WORKSPACE_DIR、TEMPLATES_DIR、safe_path()
- `server.py`：新增 `_ensure_workspace_init()`，启动时复制模板
- `tools/read_file.py`、`write_file.py`、`edit_file.py`：集成 safe_path() 路径校验
- 新增 `workspace/wiki/skills/`：技能经验积累机制

**Wiki 维护规范**
- 知识页：concepts/（概念）、entities/（实体）子目录
- 技能页：skills/ 子目录，满足条件时自动记录
- skills/index.md：技能索引，自动同步

### v0.4 (2026-04-21)

**Telegram Bot 接入（Long Polling 重构）**
- `channel/telegram.py`：重写，新增 `start_polling(on_message)` Long Polling 主循环，无需 ngrok
- `server.py`：新增 `lifespan` 启动钩子，服务启动时自动创建 polling Task
- `server.py`：`/webhook/telegram` 路由保留作为备用通道
- `channel/telegram.py`：`send_message` 保留，每条消息独立 asyncio.Task 互不阻塞

### v0.3 (重构 - 2026-04-21)

**死代码清理**
- `registry.py`：删除旧 ReAct 文本模式遗留的 `TOOLS` 字典、`execute()`、`get_tool_names()`、`get_tool_descriptions()`；`@tool` 装饰器改为 noop 保持工具文件不变
- `client.py`：删除未使用的 `one_chat()` 和 `think()` 旧接口方法
- `agent.py`：删除 `ReActAgent = ToolCallAgent` 别名行
- `server.py`：删除 `GET /todo` 死端点、重复的 `# 对话端点` 注释、函数内 `import time` 局部导入
- `index.html`：删除 `deleteSession` 中的空 `else` 块

**重命名统一**
- 全局将 `ReActAgent` 替换为 `ToolCallAgent`（涉及 `server.py`、`task_manager.py`、`main.py`、`agent.py`）
- `server.py` 版本号 `0.2` → `0.3`

**公共函数抽取（4.1）**
- `server.py` 新增 `_poll_task_events(task_id, start_index)`：复用于 `task_stream` 和 `chat_stream`，消除 ~35 行重复轮询逻辑
- `server.py` 新增 `_SSE_HEADERS` 常量、`_sse_payload()` 辅助函数

**前端公共函数抽取（5.1）**
- `index.html` 新增 `attachStreamHandlers(es, opts)`：统一处理所有 SSE 事件类型，消除 `resumeTask` 和 `send` 中 ~120 行重复的 `onmessage/onerror` 代码

**注释补充（2.4/5.3）**
- `index.html` `currentTaskId` 声明处加注释，说明与 `sessionTaskMap` 双份状态的设计原因

### v0.2 (2026-04-20)
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

*最后更新: 2026-04-24*