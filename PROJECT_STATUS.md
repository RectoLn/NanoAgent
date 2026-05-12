# NanoAgent v0.9 - 项目进度总结

## 项目概述

NanoAgent 是一个基于 ReAct 模式的轻量级 AI Agent 实现，采用 FastAPI 后端 + Vue 3 前端，支持多模型 LLM 调用、工具系统、任务管理和会话持久化。

## 代码结构

```
app/
├── agent.py              # Tool Call 主循环与 SSE 事件编排
├── compression.py        # CompressionMixin：L1/L2 压缩、摘要解析、兜底摘要与审计记录
├── subagent_runner.py    # 父 Agent 侧 run_subagent 线程/队列事件转发
├── prompt_loader.py      # Markdown prompt 加载与占位符渲染
├── llm/                  # LLM Client 封装层
│   ├── client.py         # OpenAI-compatible adapter
│   ├── provider_config.py # 从 config.yaml + .env 解析 provider 配置
│   └── types.py          # LLMResponse / ToolCall / Usage DTO
├── registry.py           # 工具执行器、OpenAI Tool Call schema 与 dispatch 辅助
├── session_manager.py    # 会话持久化管理（文件夹存储）
├── todo_manager.py       # Todo 状态管理；每个 Agent/session 独立持有实例
├── server.py             # FastAPI 服务端点
├── config.yaml           # 配置参数（provider presets, max_steps, compression 等）
├── prompts/              # Prompt 模板
│   ├── system.md         # 主 Agent 系统提示模板
│   ├── subagent_system.md # 子 Agent 系统提示模板
│   ├── subagent_summary.md # 子任务摘要模板
│   ├── compression_summary.md # L2 摘要模板
│   ├── compression_summary_fallback.md # 兜底摘要模板
│   └── compression_subagent_hint.md # 压缩后子任务派发提示
├── channel/              # 消息平台接入层
│   ├── __init__.py      # 包初始化
│   └── telegram.py      # Telegram Bot API 封装
├── tools/                # 工具实现目录
│   ├── bash.py          # Bash 命令执行
│   ├── edit_file.py     # 文件编辑
│   ├── read_file.py     # 文件读取
│   ├── web_fetch.py     # 网页抓取
│   ├── websearch.py     # Tavily 联网搜索
│   ├── write_file.py    # 文件写入
│   ├── todo.py          # Todo 管理
│   ├── compact.py       # 主动上下文压缩触发器
│   ├── current_time.py  # 当前时间
│   ├── system_info.py   # 系统信息
│   ├── install_skill.py # ClawHub/GitHub Skill 安装
│   ├── summarize.py     # 摘要 transcript 格式化辅助（内部使用，非 LLM 可见）
│   ├── subagent.py      # run_subagent 子任务隔离执行工具
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
- **Provider 化多模型支持**：DeepSeek、Kilo、Ollama、Custom provider presets 统一配置在 `config.yaml`
- **工具系统**：`registry.py` 通过 `TOOL_EXECUTORS` 和 `TOOLS_SCHEMA` 显式注册工具，工具文件保留 `@tool` 装饰器作为兼容标记
- **联网搜索工具**：`websearch` 使用 Tavily Search API，支持最新信息、新闻、财经、时间范围和域名过滤搜索
- **子 Agent 派发**：`run_subagent` 可将独立调研、分析、爬取、批处理、报告任务隔离到子 Agent 执行，支持单任务和批量并发，完成后只把结构化摘要返回父 Agent
- **子 Agent 可视化**：前端以专用卡片展示子任务描述、运行状态、内部工具步骤和最终结构化摘要；运行中即可展开内部调用，工具步骤采用单行缩略展示
- **Prompt 模板化**：主系统提示、压缩摘要、兜底摘要、子 Agent 系统提示和子任务摘要均拆分到 `app/prompts/*.md`
- **Web UI**：FastAPI SSE 流式输出 + Vue 3 响应式前端
- **实时流式**：逐 token 实时渲染，支持中断恢复

### ✅ 会话管理 (P0 - 已完成)
- **多轮对话**：上下文传递，支持连续对话
- **会话持久化**：每个 session 独立 JSON 文件存储
- **原子写入**：session JSON 使用临时文件 + `os.replace()` 保存，降低并发写入或崩溃导致的文件损坏风险
- **会话切换**：前端支持创建/删除/切换会话
- **自动恢复**：页面刷新后恢复上次会话
- **展示历史 / 模型上下文分离**：`display_messages` 保存完整 UI 历史，`messages` 仅作为可压缩的 LLM 上下文

### ✅ 任务管理 (Todo)
- **多步骤规划**：Agent 自动分解复杂任务
- **进度跟踪**：实时更新任务状态（pending/in_progress/completed/cancelled）
- **视觉反馈**：右侧面板显示任务进度条和状态
- **会话绑定**：任务状态与当前会话持久化关联
- **独立运行**：任务在后端独立线程执行，支持前端断开重连
- **中断恢复**：切换会话/刷新不影响任务执行，前端可重新观察
- **内存淘汰**：后台任务保留上限为 200 个，超过后按 `created_at` 淘汰最早任务

### ✅ 用户体验优化
- **响应式布局**：支持桌面/移动端，三栏自适应
- **中断恢复**：loading 时可切换会话，自动中断当前流，支持任务重连
- **错误处理**：网络错误、模型异常的友好提示
- **面板折叠**：左侧会话列表和右侧任务面板支持折叠
- **子 Agent 卡片**：运行中默认展开，内部工具调用开始时立即显示；完成后折叠为摘要；历史会话从 trace events 和 tool observation 恢复步骤与摘要卡片；刷新或切回页面后通过 active task + SSE 重连继续接收新的内部工具步骤

### ✅ 部署支持
- **Docker 化**：Dockerfile + docker-compose.yml 一键部署
- **跨平台**：Linux/macOS/Windows Docker Desktop 支持
- **环境配置**：.env 文件配置 API Key，支持多提供商

### ✅ Telegram Bot 接入
- **Long Polling**：`TELEGRAM_POLLING_ENABLED=true` 时服务启动即自动拉取消息，无需 ngrok 或公网地址
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

### ✅ 上下文压缩稳定性
- **三层压缩策略**：Layer 1 压缩旧 tool 结果，Layer 2 生成 LLM 摘要，Layer 3 在异常时本地兜底
- **压缩逻辑模块化**：`CompressionMixin` 已从 `agent.py` 拆到 `compression.py`，保留原有状态流语义，同时让主循环更聚焦
- **压缩 prompt 外置**：`compression.layer2.summary.prompt` / `fallback_prompt` / `subagent_hint_prompt` 可在配置中指定 Markdown 模板
- **摘要重试机制**：记录 `summary_finish_reason`，遇到 `length` 截断或半截 JSON 自动使用更大 `retry_max_tokens` 重试
- **独立摘要模型**：`SUMMARY_LLM_*` 可单独配置摘要 provider/model，例如 Docker 内访问宿主机 Ollama
- **独立子 Agent 模型**：`SUBAGENT_LLM_*` 可单独配置子 Agent provider/model；未设置时继承父 Agent 当前 provider/model
- **父 Agent 事件转发解耦**：`subagent_runner.py` 负责 `run_subagent` 的线程、队列轮询和 trace 事件转发，`agent.py` 只保留主流程编排
- **兜底摘要增强**：LLM 摘要失败时继承既有 `[上下文摘要]`，避免多次压缩后丢失核心任务进展
- **压缩后行为保持**：压缩后的上下文会追加子任务派发提示，避免长任务压缩后忘记使用 `run_subagent` 隔离探索分支
- **状态去重与裁剪**：`Authoritative Session State` 对近似重复约束做归一化合并，observations 保留最近 80 条
- **压缩审计字段**：`compression_history` 记录 fallback、错误原因、重试状态、输入字符数和估算 token

### ✅ LLM Client 封装层
- **DTO 边界**：Agent 层只依赖 `LLMResponse / ToolCall / Usage`，不再直接访问 OpenAI SDK 原始对象
- **统一 adapter**：`app/llm/client.py` 作为 OpenAI-compatible adapter，兼容 DeepSeek / Kilo / Ollama / Custom
- **Provider presets 外置**：`app/config.yaml` 的 `providers:` 块定义 base_url、default_model、api_key_env，新增 provider 无需改 Python 代码
- **前端 provider 一级选择**：Web UI 从 `/meta` 获取 provider 列表，选择结果存入 localStorage；默认使用 provider 的 `default_model`
- **摘要模型隔离**：`LLMClient(purpose="summary")` 优先读取 `SUMMARY_LLM_*`，不受前端聊天 provider 选择影响
- **子 Agent 模型隔离/继承**：`LLMClient(purpose="subagent")` 优先读取 `SUBAGENT_LLM_*`；未配置时使用父 Agent 显式传入的 provider/model

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
   - ✅ 已完成：`run_subagent` 子任务隔离执行，支持父 Agent 派发独立任务并接收结构化摘要
   - ✅ 已完成：批量子任务并发执行、运行中 trace 事件、前端步骤可视化和会话恢复
   - 🔄 待完善：多 Agent 间长期状态共享、任务队列持久化和更细粒度可观测性

### 🔄 长期愿景 (P2 - 高级特性)
1. **上下文压缩** 
   - ✅ 已完成：自动压缩触发、LLM 摘要生成、session 内置 compression_history 审计记录
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
- `_save_session(session_id)`: 使用临时文件 + `os.replace()` 原子保存单个会话到 JSON
- `_load()`: 启动时加载所有会话文件
- `create(system_prompt)`: 新建会话
- `get(session_id)`: 获取会话
- `get_or_create(session_id, system_prompt)`: 获取或创建
- `delete(session_id)`: 删除会话

#### TaskManager (task_manager.py)
- `TaskManager()`: 单例，管理所有后台任务
- `start_task(session_id, question, agent, history)`: 启动后台任务，返回 task_id
- `_evict()`: 当任务数量超过 `_MAX_TASKS=200` 时按 `created_at` 淘汰最早任务
- `get_task(task_id)`: 获取任务状态
- `get_latest_task_for_session(session_id, active_only=True)`: 获取指定 session 最新运行中任务元数据，用于刷新后恢复观察流
- `get_events_from_index(task_id, last_index)`: 获取新事件用于回放
- `is_task_done(task_id)`: 检查任务是否完成

#### ToolCallAgent (agent.py)
- `ToolCallAgent(llm)`: 初始化 Agent
- `ToolCallAgent(..., todo, tools_override, system_prompt)`: 支持为子 Agent 注入独立 Todo、工具集合和系统提示
- `run_iter(question, history=None)`: 核心 Tool Call 循环生成器
- `run(question)`: 阻塞式执行

#### CompressionMixin (compression.py)
- `estimate_tokens(messages)`: 估算上下文 token，用于压缩触发判断
- `micro_compact(messages)`: L1 静默压缩旧 tool 结果，并将 observation 摘要写入 session state
- `auto_compact(messages)`: L2/L3 上下文压缩，调用 summary LLM、解析 state patch、重建压缩锚点并记录 `compression_history`

#### Subagent Runner (subagent_runner.py)
- `run_subagent_with_events(...)`: 父 Agent 侧包装器，启动 `run_subagent` 工具线程，持续转发子 Agent trace 事件，并返回最终 summary 作为 tool observation

#### Prompt Loader (prompt_loader.py)
- `load_prompt(path)`: 从 `app/prompts/` 或显式 `prompts/...` 路径读取 Markdown prompt
- `render_prompt(path, **values)`: 读取 prompt 并替换 `{name}` 占位符

#### FastAPI 端点 (server.py)
- `GET /`: 返回前端页面
- `GET /chat/stream`: SSE 流式对话（启动后台任务）
- `GET /tasks/{task_id}/stream`: SSE 任务观察流（纯观察接口）
- `POST /chat`: 阻塞式对话
- `GET /sessions`: 列出会话摘要
- `POST /sessions`: 新建会话
- `GET /sessions/{sid}`: 获取会话详情；若存在运行中后台任务，会附带 `active_task`
- `DELETE /sessions/{sid}`: 删除会话
- `POST /webhook/telegram`: 接收 Telegram Webhook 推送（备用），非文字消息忽略，文字消息后台处理并回复

#### 公共辅助 (server.py)
- `_poll_task_events(task_id, start_index)`: SSE 事件轮询生成器，`chat_stream` 和 `task_stream` 共用；`start_index` 使用前端已收到的公开事件序号，跳过内部持久化事件，并为推送事件附加 `event_index`
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

#### 子 Agent 工具 (tools/subagent.py)
- `run_subagent(task, context="", event_queue=None, call_id="", parent_provider="", parent_model_id="", max_concurrency=3)`: 派发独立子任务；`task` 可为字符串或任务对象数组 `[{id, task, context?}]`，批量模式按 `max_concurrency` 并发执行。子 Agent 拥有除 `run_subagent` 外的常规工具，完成后返回结构化摘要；可通过父 Agent 透传 provider/model
- `_build_sub_tools()`: 构造子 Agent 工具集合，禁止递归子任务
- `_emit_task_start()` / `_emit_step()` / `_emit_done()`: 向父 Agent 推送子任务 trace 事件，覆盖 task_start、tool_start、tool_result、task_done
- `_summarize(llm, messages, task)`: 使用 `subagent_summary.md` 将子 Agent 历史压缩为父 Agent 可用摘要
- `_SUBAGENT_TIMEOUT`: 子 Agent 线程等待上限，当前为 600 秒，超时返回降级消息

#### 联网搜索工具 (tools/websearch.py)
- `websearch(query, max_results=5, search_depth="basic", topic="general", time_range="", include_domains=None, exclude_domains=None, include_answer=False, include_raw_content=False)`: 使用 Tavily Search API 搜索并返回 Markdown 风格结果
- `TAVILY_API_KEY`: 必需环境变量；缺失时工具返回配置提示
- 结果包含标题、URL、摘要、相关度、发布时间和响应元数据，输出超过 12000 字符会截断

#### 前端公共函数 (static/index.html)
- `attachStreamHandlers(es, opts)`: 统一绑定 SSE `onmessage`/`onerror`，`send` 和 `resumeTask` 共用
- `applySubagentTrace(cards, ev)`: 将 `subagent_step` trace 事件应用到单个或批量子 Agent 卡片
- `upsertSubagentStep(steps, ev)`: 按 `sub_call_id` 原地更新子 Agent 内部工具步骤，运行中显示一行缩略，结果到达后关闭 running 状态
- `normalizeTaskInfo()` / `getSessionTaskInfo()`: 统一解析后端 `active_task`、内存映射和 localStorage 中的任务恢复信息
- `reconnectCurrentTask()`: 页面重新可见或 SSE 临时断开时，按 `lastEventIndex` 继续订阅当前任务

### 📊 重要变量

#### 环境变量 (.env)
- `LLM_PROVIDER`: 默认聊天 provider（deepseek / kilo / ollama / custom）
- `LLM_MODEL_ID`: 可选聊天模型覆盖；留空使用 `config.yaml` 中 provider 的 `default_model`
- `LLM_API_KEY`: 通用 OpenAI-compatible API key fallback
- `LLM_BASE_URL`: 可选 OpenAI-compatible endpoint 显式覆盖
- `DEEPSEEK_API_KEY`: DeepSeek provider API Key
- `KILO_API_KEY`: Kilo provider API Key
- `SUMMARY_LLM_PROVIDER`: 可选摘要 provider；留空复用默认聊天 provider
- `SUMMARY_LLM_API_KEY`: 可选摘要 API Key
- `SUMMARY_LLM_BASE_URL`: 可选摘要 endpoint 覆盖，常用于 Docker 访问本地 Ollama
- `SUMMARY_LLM_MODEL_ID`: 可选摘要模型覆盖
- `SUBAGENT_LLM_PROVIDER`: 可选子 Agent provider；留空继承父 Agent 当前 provider/model
- `SUBAGENT_LLM_API_KEY`: 可选子 Agent API Key
- `SUBAGENT_LLM_BASE_URL`: 可选子 Agent endpoint 覆盖
- `SUBAGENT_LLM_MODEL_ID`: 可选子 Agent 模型覆盖
- `TAVILY_API_KEY`: Tavily Search API Key，用于 `websearch` 联网搜索工具
- `TELEGRAM_BOT_TOKEN`: Telegram Bot Token（由 @BotFather 获取，可选）
- `TELEGRAM_POLLING_ENABLED`: 设为 `true` 才启动 Long Polling（默认 false，防多实例抢占）

#### 全局状态
- `SESSION_MGR`: SessionManager 单例
- `TASK_MGR`: TaskManager 单例 (task_manager.py)
- `TodoManager`: 每个 Agent/session 独立持有的任务状态管理器 (todo_manager.py)
- `TOOLS_SCHEMA`: 工具描述列表 (registry.py)

#### 前端状态 (static/index.html)
- `timeline`: 当前会话消息数组
- `todos`: 当前任务列表
- `sessions`: 会话摘要列表
- `currentSessionId`: 当前会话 ID
- `currentTaskId`: 当前任务 ID
- `currentEventSource`: 当前活跃的 EventSource
- `selectedProvider`: 当前聊天 provider，下拉框选择后写入 localStorage

### 🛠️ 配置参数 (config.yaml)
```yaml
default:
  provider: deepseek

providers:
  deepseek:
    base_url: https://api.deepseek.com
    default_model: deepseek-chat
    api_key_env: DEEPSEEK_API_KEY
  kilo:
    base_url: https://api.kilo.ai/api/gateway
    default_model: kilo-auto/free
    api_key_env: KILO_API_KEY
  ollama:
    base_url: http://host.docker.internal:11434/v1
    default_model: qwen3:8b
    api_key_env: null

agent:
  max_steps: 200         # 最大推理步骤
  temperature: 0.1       # LLM 温度参数
  max_tokens: 16384      # 单次 LLM 调用最大输出 token
  nag_threshold: 3       # 连续未调用 todo 工具时注入提醒

prompts:
  system: prompts/system.md  # 系统提示文件路径

compression:
  layer2:
    token_threshold: 50000
    message_threshold: 100
    summary:
      prompt: compression_summary.md
      fallback_prompt: compression_summary_fallback.md
      subagent_hint_prompt: compression_subagent_hint.md
```

### 📝 工具注册模式 (registry.py)
```python
TOOL_EXECUTORS = {
    "bash": _exec_bash,
    "web_fetch": _exec_web_fetch,
    "websearch": _exec_websearch,
    "run_subagent": _exec_subagent,
}

TOOLS_SCHEMA = [
    {"type": "function", "function": {"name": "websearch", ...}},
]

def execute_tool_call(name, args_json, executors=None):
    # 默认从 TOOL_EXECUTORS 查找 executor；子 Agent 可传入裁剪后的 executors
    # JSON 参数解析后以 kwargs 调用
```

## 开发环境

- **Python**: 3.8+
- **依赖**: fastapi, uvicorn, openai, pyyaml, python-dotenv
- **前端**: Vue 3 + Marked.js
- **部署**: Docker + docker-compose

## 更新日志

### v0.9 (2026-05-13)

**子 Agent 恢复稳定性与 Agent 内核整理**
- `app/server.py`：`GET /sessions/{sid}` 附带当前 session 的 `active_task`，前端刷新后即使 localStorage 映射失效，也能重新订阅仍在运行的后台任务。
- `app/server.py`：`/tasks/{task_id}/stream` 使用公开事件序号 `event_index` 做断点续传，跳过 `message_delta` / `context_snapshot` 等内部持久化事件，避免前端索引和后端原始事件数组错位。
- `app/server.py`：任务已结束但重连时未推到 `done` 的场景会补发 `done`，避免前端残留任务映射后反复重连。
- `app/static/index.html`：刷新/切换会话恢复历史卡片时同时注册到 `callCards`，后续 live `subagent_step` 可继续追加到同一张子 Agent 卡片。
- `app/static/index.html`：SSE 临时断开或页面重新可见时按 `lastEventIndex` 自动恢复观察流，子 Agent 新工具调用可继续动态渲染。
- 新增 `app/compression.py`：将 `estimate_tokens()`、`micro_compact()`、`auto_compact()`、摘要解析、兜底摘要和压缩审计记录迁入 `CompressionMixin`，并在类注释中显式列出对 `ToolCallAgent` 的依赖。
- 新增 `app/subagent_runner.py`：封装父 Agent 执行 `run_subagent` 时的线程启动、队列轮询和 trace 事件转发，`agent.py` 主循环只保留 `yield from run_subagent_with_events(...)`。
- `app/registry.py`：`execute_tool_call()` 支持 `executors` 参数，主 Agent 和子 Agent 可共用同一套 dispatch 逻辑，避免 `agent.py` 中重复解析 JSON 和调用工具。
- `app/agent.py`：保留核心 Tool Call loop、usage 统计、SSE 事件和 LLM 调用前权威状态注入；上下文压缩和 subagent 运行细节已迁出，文件规模从约 981 行降至约 525 行。
- README / README_zh / PROJECT_STATUS 同步更新项目结构、测试说明、工具注册模式和子 Agent 刷新恢复链路。
- 已验证：`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_state_flow.py tests/test_subagent_stability.py` 全部通过；`PYTHONPYCACHEPREFIX=/tmp/nanoagent_pycache python3 -m py_compile app/server.py app/task_manager.py` 通过。

### v0.9 (2026-05-12)

**子 Agent 批量并发与运行中可观测性**
- `app/tools/subagent.py`：`run_subagent` 支持单任务字符串和任务对象数组 `[{id, task, context?}]`，批量模式按 `max_concurrency` 并发执行。
- `app/tools/subagent.py`：新增 task/tool 级 trace 事件，覆盖 `task_start`、`tool_start`、`tool_result`、`task_done`，子工具调用发起时即可推送给父 Agent。
- `app/agent.py`：父 Agent 执行 `run_subagent` 时启动工具线程并持续转发子 Agent trace 事件，不再等子任务完成后才让前端看到内部流程。
- `app/static/index.html`：子 Agent 卡片运行中默认展开；内部工具调用以单行缩略展示（工具名、参数摘要、运行状态点），避免 observation 预览撑开页面。
- `app/static/index.html`：新增批量子 Agent 容器，展示每个子任务的独立状态、步骤和摘要，支持会话切换/刷新后的 trace 恢复。
- `app/session_manager.py`、`app/server.py`、`app/task_manager.py`：保存 `trace_events`，历史会话可恢复子 Agent 内部步骤与最终摘要。
- `tests/test_subagent_stability.py`：测试覆盖子任务运行中事件、父 Agent SSE 转发和子 Agent provider/model 继承逻辑。
- README / README_zh / PROJECT_STATUS 更新到 v0.9，并同步批量子任务、运行中展开和单行工具步骤说明。

### v0.8.5 (2026-05-11)

**子 Agent 可视化与稳定性测试**
- `app/tools/subagent.py`：子 Agent 执行内部工具调用时发出 `subagent_step` 事件，完成后返回带 `##` 分块的结构化摘要。
- `app/agent.py`：父 Agent 执行 `run_subagent` 时转发子 Agent 步骤事件，并把最终摘要作为 tool observation 写入会话历史。
- `app/static/index.html`：新增子 Agent 专用卡片；运行中默认展开，展示内部 Steps 列表，完成后自动折叠并展示最终摘要；历史会话可恢复摘要卡片。
- `tests/test_subagent_stability.py`：新增子 Agent 稳定性测试，覆盖步骤事件、父 Agent SSE 转发和 `SUBAGENT_LLM_*` 配置优先级。
- README / README_zh / PROJECT_STATUS 同步更新子 Agent 可视化、测试脚本和独立 API 配置说明。

### v0.8.4 (2026-05-11)

**子 Agent 模型路由隔离**
- `app/llm/provider_config.py`：新增 `purpose="subagent"` 解析分支，优先读取 `SUBAGENT_LLM_PROVIDER`、`SUBAGENT_LLM_API_KEY`、`SUBAGENT_LLM_BASE_URL`、`SUBAGENT_LLM_MODEL_ID`。
- `app/llm/client.py`：暴露解析后的 `provider`、`base_url`、`model`，用于父 Agent 向子 Agent 透传当前模型配置。
- `app/agent.py`：父 Agent 调用 `run_subagent` 时传入当前 provider/model；若未设置 `SUBAGENT_LLM_*`，子 Agent 会继承 Web UI 当前选择。
- `app/tools/subagent.py`：子 Agent 改用 `LLMClient(purpose="subagent", override=parent_override)` 初始化，支持独立配置和父配置继承。
- `.env.example` / `.env`：新增子 Agent 独立 LLM 配置项，可为子 Agent 单独配置 OpenAI-compatible API。
- README / README_zh / PROJECT_STATUS 同步更新环境变量、子 Agent 模型路由说明。

### v0.8.3 (2026-05-11)

**联网搜索工具与稳定性维护**
- 新增 `app/tools/websearch.py`：通过 Tavily Search API 提供 `websearch` 工具，支持 `max_results`、`search_depth`、`topic`、`time_range`、`include_domains`、`exclude_domains`、`include_answer` 和 `include_raw_content`。
- `app/registry.py`：新增 `_exec_websearch()`、`TOOL_EXECUTORS["websearch"]` 和 OpenAI Tool Call schema，模型可直接调用联网搜索。
- `.env.example`：新增 `TAVILY_API_KEY`，用于配置 Tavily Search API Key。
- `app/session_manager.py`：session JSON 保存改为临时文件 + `os.replace()` 原子写入。
- `app/task_manager.py`：新增 `_MAX_TASKS = 200`、`TaskState.created_at` 和 `_evict()`，避免后台任务无限增长。
- `app/tools/subagent.py`：新增 `_SUBAGENT_TIMEOUT = 600`，子 Agent 超时返回降级提示，避免父任务永久阻塞。
- `app/server.py`：修复取消任务接口中的乱码错误文案为 `"任务不存在"`。
- README / README_zh / PROJECT_STATUS 同步更新工具列表、环境变量和注册模式说明。

### v0.8.2 (2026-05-08)

**子 Agent 派发与 Prompt 模板化**
- 新增 `app/tools/subagent.py`：提供 `run_subagent(task, context)` 工具，用独立 `ToolCallAgent` 执行调研、分析、爬取、批处理、报告等独立子任务，隔离探索历史，完成后只返回结构化摘要。
- `ToolCallAgent` 构造参数扩展：支持注入 `todo`、`tools_override`、`system_prompt`，子 Agent 可使用独立 Todo 状态和精简工具集，并禁止递归调用 `run_subagent`。
- 新增 `app/prompt_loader.py`：统一加载并渲染 `app/prompts/*.md`，替代散落在代码里的 prompt 字符串。
- 新增 prompt 文件：`subagent_system.md`、`subagent_summary.md`、`compression_summary.md`、`compression_summary_fallback.md`、`compression_subagent_hint.md`。
- `app/prompts/system.md` 增加子任务派发规则：规划完成后判断独立调研/分析/整理/抓取/批处理/报告类步骤是否应使用 `run_subagent`。
- 上下文压缩 L2 摘要 prompt 改为配置驱动：`compression.layer2.summary.prompt`、`fallback_prompt`、`subagent_hint_prompt`，压缩后追加短提示以保持子任务派发行为。
- `app/config.yaml`：Ollama 默认模型更新为 `qwen3:8b`，L2 token 触发阈值更新为 `50000`，摘要 prompt 文件路径写入配置。
- `docker-compose.yml` 增加 `extra_hosts: host.docker.internal:host-gateway`，容器内可稳定访问宿主机 Ollama。
- README / README_zh / PROJECT_STATUS 同步更新子 Agent、Prompt 模板和配置说明。

### v0.8.1 (2026-05-08)

**LLM Client 封装层与 Provider 配置重构**
- 新增 `app/llm/` 封装层：`client.py`、`provider_config.py`、`types.py`，Agent 层改用 `LLMResponse / ToolCall / Usage` DTO，不再依赖 OpenAI SDK 原始 choice/message 对象。
- 删除旧 `app/client.py`，统一通过 `LLMClient` 调用 OpenAI-compatible API。
- `config.yaml` 新增 `providers:` 块，公开配置 DeepSeek / Kilo / Ollama / Custom 的 `base_url`、`default_model`、`api_key_env`；新增 provider 不再需要改 Python 代码。
- `.env` 职责收敛为 provider 选择和 secret：`LLM_PROVIDER`、`KILO_API_KEY`、`DEEPSEEK_API_KEY`，`LLM_BASE_URL` / `LLM_MODEL_ID` 只作为显式覆盖使用。
- 前端模型切换收敛为一级 provider 选择：从 `/meta` 获取 provider 列表，选择结果写入 `localStorage.selectedProvider`，发送请求时只传 provider，后端使用该 provider 的 `default_model`。
- 摘要模型独立：`auto_compact()` 使用 `LLMClient(purpose="summary")`，优先读取 `SUMMARY_LLM_*`，可将摘要任务路由到本地 Ollama。
- 已验证本地 Ollama summary：容器内通过 `SUMMARY_LLM_BASE_URL=http://172.17.0.1:11434/v1` 调用 `qwen2.5:7b` 成功返回摘要响应。
- 更新 `tests/test_state_flow.py`：测试 FakeLLM 改为新 DTO，并 mock summary client，状态流与压缩测试继续通过。

### v0.8 (2026-04-27)

**上下文压缩升级 · 三层策略架构**

**新增三层压缩架构**：
- **Layer 1 - 消息截断**：保留最近 3 条 tool 结果不截断，旧 tool 消息 content 超过 100 字符自动截断到 100 字符，减少冗长输出
- **Layer 2 - 摘要压缩**：当 token 估算超过 阈值 时，触发 LLM 摘要生成，保留最近 10 条消息不压缩
- **Layer 3 - 兜底处理**：token 溢出时直接输出现有内容，避免 context 无限堆积

**配置重构**：
- `config.yaml` 从简单的 `context.*` 改为结构化的 `compression.*` 配置
- 新增 `layer1`, `layer2` 子配置，支持精细调优
- 移除旧的 `keep_recent_messages`（现在在 layer2 中）
- 新增 `content_threshold` 控制 tool 消息截断长度

**参数意义详解**：
- `agent.max_tokens: 16384` - 单次 LLM 调用的最大输出 token（16K 适合长任务）
- `compression.enabled: true` - 全局压缩开关（false 用于调试原始对话）
- `layer1.keep_recent_tool_messages: 3` - 保留最近 3 条 tool 结果的完整 content
- `layer1.content_threshold: 100` - tool 消息 content 超过 100 字符截断（避免 bash 输出过长）
- `layer2.token_threshold: 3000` - 触发压缩的词数阈值（估算 token = 词数 × 1.3）
- `layer2.message_threshold: 30` - 触发压缩的消息数阈值
- `layer2.summary.temperature: 0.1` - 摘要生成的一致性参数
- `layer2.summary.max_tokens: 1000` - 摘要的最大长度
- `layer2.summary.max_chars: 800` - 摘要的字符数上限


**上下文压缩与 Token 统计修正**

**上下文压缩锚点增强**：
- `agent.py`：`auto_compact()` 压缩后的 messages 不再只保留单条摘要，而是保留 system prompt、第一条用户请求、压缩摘要、当前 Todo/任务状态、最新用户请求。
- `agent.py`：新建 Agent 时从 `session.tasks` 恢复 `self.todo.items`，避免跨请求后 Todo 状态丢失。
- `agent.py`：token 估算从纯空格分词扩展为 `max(words * 1.3, chars / 4)`，并纳入 `tool_calls` / `tool_call_id` 的结构成本，降低中文和工具调用场景下的低估风险。

**Token 统计拆分**：
- `session_manager.py`：保留 `token_usage` 作为会话累计消耗，新增 `context_usage` 表示最近一次 LLM 请求的当前上下文窗口占用。
- `agent.py`：`token_update` SSE 事件新增 `round_usage` 与 `context_usage`；最终 assistant message 写入 `usage`，用于刷新或切换会话后恢复回答卡片 token。
- `index.html`：会话列表显示 `ctx 当前窗口 / 模型窗口`，累计消耗通过 hover tooltip 查看；回答卡片从持久化 `msg.usage` 恢复单轮 token。

**前端 per-session loading 修正**：
- `index.html`：SSE handler 绑定创建时的 `sid` 和 `EventSource`，旧流事件不再误清新会话 loading，也不会污染当前 timeline。
- `index.html`：Landing 页发送按钮移除 `sessionLoading[null]`，避免新会话首条消息 loading 状态不一致。

**上下文压缩可靠性修正**：
- `agent.py`：摘要调用记录 `summary_finish_reason`，当 LLM 返回 `length` 且内容为空或 JSON 被截断时，自动使用 `retry_max_tokens` 重试。
- `agent.py`：LLM 摘要仍失败时使用本地 fallback，但会继承已有 `[上下文摘要]`，避免覆盖掉之前已压缩出的关键进展。
- `agent.py`：旧 tool 结果压缩为真实摘要，不再提示不存在的 `retrieve_memory()` 工具。
- `session_state.py`：新增近似重复去重，合并类似“必须使用 guizang-ppt-skill”这类重复约束，并将 observations 裁剪到最近 80 条。
- `session_manager.py`：展示历史与模型上下文分离，刷新后 UI 使用 `display_messages`，只有发给大模型的 `messages` 会被压缩。
- `config.yaml`：默认模型切换为 `deepseek:deepseek-chat`；上下文压缩参数更新为 `keep_recent_tool_messages=3`、`content_threshold=800`、`message_threshold=50`、`summary.max_tokens=1200`、`summary.retry_max_tokens=2400`、`summary.max_chars=1200`。


### v0.7 (2026-04-25)

**上下文压缩机制 · 从文件存储改为 Session JSON 内置 + Token 溢出修复**

**根本问题修复**：
- `config.yaml`：`agent.max_tokens: 4096` → `16384`（长任务常规参数容易触发截断）
- `agent.py`：`finish_reason == "length"` 改为分流处理：
  - 纯文本被截断 → 直接输出现有内容作为最终答案（不续写，避免 context 堆积）
  - 工具参数被截断 → 报错提示调高 `max_tokens`
- `config.yaml`：压缩阈值从 25000 词/50 消息降至 **6000 词/30 消息**（安全上限：32K ctx - 16K max_tokens = 16K 可用，中文 ÷1.5 = 10.7K 词，再除以 1.5 安全系数 ≈ 7K）

**压缩机制重构 · 数据存储改为自包含**：
- `tools/summarize.py`：新增 `format_messages_for_summary()`，将消息列表格式化为可读文本供 LLM 摘要
- `session_manager.py`：`Session` 类新增 `compression_history: List[Dict]` 字段 + `add_compression_record()` 方法；`_save_session()` 和 `_load()` 完整支持压缩历史序列化/反序列化
- `agent.py`：
  - `_compress_context()` 改为返回 `(new_history, log_data)` 元组
  - `run_iter()` 中 `yield {"type": "compression_log", **log_data}` 事件（不再写文件）
  - 删除 `_log_compression()` 文件操作方法
- `task_manager.py`：处理 `compression_log` 事件，自动调用 `session.add_compression_record()` 并保存
- 删除 `templates/wiki/compression.md`：无需全局日志文件，压缩记录随 session 生存销毁

**设计完成方案**：
- 每个 session 有独立的 `compression_history` 数组，记录对应会话的所有压缩操作
- 格式：`{timestamp, original_count, compressed_count, compressed_msg_count, token_saved, summary}`
- session 删除时自动清理相关压缩记录，避免孤儿数据
- 用户可通过 `/sessions/{sid}` API 查看 `compression_history` 审计完整压缩历史

### v0.6 (2026-04-24)

**Telegram 渲染修复（MarkdownV2 三级降级）**
- `channel/telegram.py`：重写消息格式化，采用 Telegram MarkdownV2 作为首选格式，支持标题、表格（转等宽代码块）、列表、粗体、斜体、行内代码、围栏代码块
- 新增 `_escape_v2`、`_escape_code_v2`、`_process_inline_v2`、`_md_to_markdownv2`、`_md_to_html_simple` 五个辅助函数
- `send_message` 实现三级降级链：MarkdownV2 → HTML → 纯文本，每级失败（400）时打日志并自动尝试下一级
- 表格处理：先剥离行内格式（**bold**、*italic*、\`code\`），再放入等宽代码块，避免内部出现转义字符
- 围栏代码块：不携带语言标识（例如 python 语言标记），防止 Telegram 解析异常（`</>` 图标）
- `.env.example`：保留 `TELEGRAM_POLLING_ENABLED=false` 说明

**Telegram 稳定性修复**
- `channel/telegram.py`：新增 `TELEGRAM_POLLING_ENABLED=true` 显式开关，token 存在但未开启时静默跳过，防止多实例（9090/9091）共享 token 互相抢占 updates
- `channel/telegram.py`：新增 `_md_to_html()` 转换函数，将 LLM CommonMark 输出转为 Telegram HTML（围栏代码块、行内代码、`**bold**`、`*italic*`），`send_message` 改用 HTML 模式发送，400 时降级纯文本
- `.env.example`：新增 `TELEGRAM_POLLING_ENABLED=false` 字段说明

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
- 旧 `app/client.py`：删除未使用的 `one_chat()` 和 `think()` 旧接口方法
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

*最后更新: 2026-05-13*
