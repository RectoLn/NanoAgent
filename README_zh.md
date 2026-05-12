# NanoAgent v0.9

一个最小化的 ReAct Agent 实现，支持 LLM 调用、工具注册、Web UI、Telegram Bot 集成，以及 ClawHub Skill 技能系统。

> [English](./README.md)

## 功能特性

- **Tool Call 循环**：基于 OpenAI Tool Call 协议的原生工具调用
- **Provider 化 LLM 支持**：OpenAI-compatible provider 在 `app/config.yaml` 中配置（DeepSeek、Kilo、Ollama、Custom）
- **工具系统**：通过 `registry.py` 的 `TOOL_EXECUTORS` 和 `TOOLS_SCHEMA` 显式注册
- **联网搜索工具**：内置 `websearch`，通过 Tavily Search API 查询最新资料、新闻、财经和域名过滤结果
- **ClawHub Skill 技能系统**：内置 `install_skill` 工具，支持从 ClawHub 自动安装技能
- **子 Agent 派发**：内置 `run_subagent` 工具，将调研、分析、批处理、报告类任务隔离到子 Agent 执行，支持批量并发
- **子 Agent 可视化**：Web UI 显示子 Agent 卡片；运行中即可展开查看内部工具调用，工具步骤以单行缩略展示，完成后折叠为结构化摘要
- **子 Agent 刷新恢复**：运行中的子 Agent 卡片在刷新、切换会话或 SSE 短暂断开后，会续接 active task 观察流并继续动态更新内部工具调用
- **Prompt 模板化**：system、压缩、兜底、子 Agent 相关 prompt 均独立存放为 Markdown 文件
- **任务管理**：多步骤任务规划与状态跟踪
- **会话持久化**：独立会话存储，自动保存到 JSON 文件
- **Web UI**：FastAPI 后端 + Vue 3 前端，流式输出
- **实时流式**：逐 token 实时输出
- **Telegram Bot**：基于 Long Polling 的消息平台集成（无需公网地址），在 Telegram 中直接与 Agent 对话
- **上下文压缩**：自动压缩长对话历史为智能摘要，防止 token 溢出，压缩记录内置存储于会话文件
- **上下文压缩锚点**：压缩后保留 system prompt、初始用户输入、最新用户输入，以及当前权威 Todo/任务状态。
- **独立摘要模型**：上下文摘要可通过 `SUMMARY_LLM_*` 单独配置，例如使用本地 Ollama，不受前端聊天 provider 影响。
- **独立子 Agent 模型**：子 Agent 可通过 `SUBAGENT_LLM_*` 单独配置；未设置时继承父 Agent 当前 provider/model。
- **摘要可靠性兜底**：记录 LLM 摘要 finish_reason，遇到截断摘要自动重试，本地兜底会继承既有摘要，避免越压越丢信息。
- **压缩后的子任务提示**：上下文压缩后保留短提示，提醒 Agent 将独立调研或批处理任务派发给子 Agent。
- **展示历史 / 模型上下文分离**：刷新页面展示完整历史，对大模型发送的上下文单独压缩。
- **Token 统计持久化**：回答卡片保存本轮 usage，刷新或切换会话后仍可恢复；会话列表区分当前上下文窗口占用和会话累计消耗。

## 子 Agent 与 Prompt 模板

NanoAgent 可以通过 `run_subagent` 工具派发独立子任务。子 Agent 使用独立 Todo 状态、精简系统提示，并拥有除递归调用 `run_subagent` 外的常规工具。子任务完成后，其完整消息历史会被丢弃，只向父 Agent 返回结构化摘要：结论、产出物路径、关键发现和未完成项。

`run_subagent` 的 `task` 参数既可以是单个字符串，也可以是任务对象数组 `[{id, task, context?}]`。批量模式会按 `max_concurrency` 并发运行多个子 Agent，并在父任务中汇总每个子任务的结果。

这个机制适合隔离容易污染主上下文的任务：调研、分析、爬取、批处理、报告生成，或将文件内容整理进 wiki。重要产出应写入 `workspace/wiki/...`，父 Agent 需要完整细节时再读取对应文件。

子 Agent 的模型路由可以通过 `SUBAGENT_LLM_PROVIDER`、`SUBAGENT_LLM_API_KEY`、`SUBAGENT_LLM_BASE_URL`、`SUBAGENT_LLM_MODEL_ID` 单独配置。若这些变量都未设置，父 Agent 会把当前使用的 provider/model 显式传给 `run_subagent`，因此子 Agent 会跟随 Web UI 中选择的 provider。

父 Agent 调用 `run_subagent` 时，Web UI 会显示专门的子 Agent 卡片。运行中默认展开，并在子 Agent 发起内部工具调用时立即显示步骤；每个内部工具调用只占一行缩略信息（工具名 + 参数摘要 + 运行状态点），避免长 observation 撑开页面。完成后卡片自动折叠为最终结构化摘要。

历史会话可从保存的 trace 事件和 tool observation 恢复内部步骤与摘要卡片。如果父任务仍在运行，session API 会返回 active task 元数据，前端按最后收到的公开 `event_index` 重新连接 `/tasks/{task_id}/stream`，因此刷新或切换页面回来后，新的子 Agent 工具调用仍会追加到恢复出的卡片上。

Prompt 文本集中放在 `app/prompts/`，由 `app/prompt_loader.py` 加载，调整行为时不需要改 Agent 主循环：

- `system.md`：主 Agent 系统提示
- `subagent_system.md`：子 Agent 系统提示
- `subagent_summary.md`：子任务摘要提示
- `compression_summary.md`：常规 L2 上下文摘要提示
- `compression_summary_fallback.md`：兜底摘要提示
- `compression_subagent_hint.md`：压缩后插入的子任务派发提醒

## 上下文与 Token 统计

NanoAgent 将三个容易混淆的 token 指标拆开处理：

- **单轮回答 usage**：写入 assistant message 的 `usage` 字段，用于恢复回答卡片上的输入/输出 token。
- **当前上下文窗口**：写入 session 的 `context_usage` 字段，表示最近一次请求的 prompt/window 占用，前端显示为 `ctx 当前 / 模型窗口`。
- **会话累计消耗**：写入 session 的 `token_usage` 字段，表示整个会话累计花费，可超过模型窗口，只作为成本/历史统计。

上下文压缩不会只留下单条摘要，而是保留稳定锚点：system prompt、第一条用户请求、压缩摘要、当前 Todo/任务状态、最新用户请求。UI 展示历史与模型上下文分离，刷新后仍展示完整对话，只有发送给大模型的部分会被压缩。

## 快速开始

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 API Key

# 2. Docker 启动
docker compose up -d

# 3. 浏览器访问
http://localhost:9090
```

## Windows Docker 环境设置

1. **安装 Docker Desktop**：
   - 从 [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/) 下载
   - 安装并启动 Docker Desktop
   - 确保启用 WSL2（推荐以获得更好性能）

2. **运行服务**：
   ```cmd
   cd C:\path\to\NanoAgent
   docker-compose up --build
   ```

3. **访问 Web UI**：
   - 浏览器打开 `http://localhost:9090`

**注意**：确保 9090 端口可用。Docker Desktop 提供了完整的容器化环境，适合开发和部署。

Docker Compose 已将 `host.docker.internal` 映射到宿主机，因此容器内可以通过 `http://host.docker.internal:11434/v1` 访问宿主机上的 Ollama。

## 环境变量

| 变量 | 说明 |
|------|------|
| `LLM_PROVIDER` | 默认聊天 provider（`deepseek` / `kilo` / `ollama` / `custom`） |
| `LLM_MODEL_ID` | 可选的聊天模型覆盖；留空使用 `app/config.yaml` 中的 provider preset |
| `LLM_API_KEY` | 通用 OpenAI-compatible API key fallback |
| `LLM_BASE_URL` | 可选的 OpenAI-compatible endpoint 显式覆盖 |
| `DEEPSEEK_API_KEY` | DeepSeek provider API Key |
| `KILO_API_KEY` | Kilo provider API Key |
| `SUMMARY_LLM_PROVIDER` | 可选摘要 provider；留空复用默认聊天 provider |
| `SUMMARY_LLM_API_KEY` | 可选摘要 API Key |
| `SUMMARY_LLM_BASE_URL` | 可选摘要 endpoint 覆盖，常用于 Docker 访问本地 Ollama |
| `SUMMARY_LLM_MODEL_ID` | 可选摘要模型覆盖 |
| `SUBAGENT_LLM_PROVIDER` | 可选子 Agent provider 覆盖；不设置则继承父 Agent 当前 provider/model |
| `SUBAGENT_LLM_API_KEY` | 可选子 Agent API Key |
| `SUBAGENT_LLM_BASE_URL` | 可选子 Agent endpoint 覆盖 |
| `SUBAGENT_LLM_MODEL_ID` | 可选子 Agent 模型覆盖 |
| `TAVILY_API_KEY` | Tavily Search API Key，用于 `websearch` 联网搜索工具 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token（由 @BotFather 创建） |
| `TELEGRAM_POLLING_ENABLED` | 设为 `true` 才启动 Telegram Long Polling |

## 配置选项

Agent 行为可以通过 `app/config.yaml` 自定义：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `default.provider` | 首次加载时使用的默认聊天 provider | deepseek |
| `providers.<name>.base_url` | provider 的 OpenAI-compatible endpoint preset | 视 provider 而定 |
| `providers.<name>.default_model` | 未覆盖模型时使用的 provider 默认模型 | 视 provider 而定 |
| `providers.<name>.api_key_env` | 该 provider 对应的 API key 环境变量名 | 视 provider 而定 |
| `agent.max_steps` | 每次查询的最大推理步骤 | 200 |
| `agent.temperature` | LLM 温度参数（创造性 vs 一致性） | 0.1 |
| `agent.max_tokens` | 每次 LLM 调用的最大输出 token 数 | 16384 |
| `agent.nag_threshold` | 未调用 todo 工具的连续轮数阈值（注入提醒） | 3 |
| `compression.enabled` | 启用/禁用自动上下文压缩 | true |
| `compression.layer1.keep_recent_tool_messages` | 保留最近 N 条完整 tool 结果 | 3 |
| `compression.layer1.content_threshold` | 旧 tool 结果超过该字符数后压缩为摘要 | 200 |
| `compression.layer2.token_threshold` | 估算 token 超过该值时触发 L2 摘要压缩 | 50000 |
| `compression.layer2.message_threshold` | 消息数超过该值时触发 L2 摘要压缩 | 100 |
| `compression.layer2.summary.prompt` | 常规 L2 摘要 prompt 文件 | compression_summary.md |
| `compression.layer2.summary.fallback_prompt` | 常规模板不可用时的兜底摘要 prompt 文件 | compression_summary_fallback.md |
| `compression.layer2.summary.subagent_hint_prompt` | 压缩后插入的子任务派发提示文件 | compression_subagent_hint.md |
| `compression.layer2.summary.max_tokens` | 摘要模型常规输出预算 | 1200 |
| `compression.layer2.summary.retry_max_tokens` | 摘要被截断时的重试输出预算 | 2400 |
| `compression.layer2.summary.max_chars` | 解析后写入上下文的摘要字符上限 | 1200 |

**config.yaml 示例：**
```yaml
default:
  provider: "deepseek"

providers:
  deepseek:
    label: "DeepSeek"
    base_url: "https://api.deepseek.com"
    default_model: "deepseek-chat"
    api_key_env: "DEEPSEEK_API_KEY"
  kilo:
    label: "Kilo"
    base_url: "https://api.kilo.ai/api/gateway"
    default_model: "kilo-auto/free"
    api_key_env: "KILO_API_KEY"
  ollama:
    label: "Ollama"
    base_url: "http://host.docker.internal:11434/v1"
    default_model: "qwen3:8b"
    api_key_env: null

agent:
  max_steps: 200
  temperature: 0.1
  max_tokens: 16384
  nag_threshold: 3

compression:
  enabled: true
  layer1:
    keep_recent_tool_messages: 3
    content_threshold: 200
  layer2:
    token_threshold: 50000
    message_threshold: 100
    summary:
      prompt: "compression_summary.md"
      fallback_prompt: "compression_summary_fallback.md"
      subagent_hint_prompt: "compression_subagent_hint.md"
      temperature: 0.1
      max_tokens: 1200
      retry_max_tokens: 2400
      max_chars: 1200
```

## Telegram Bot

NanoAgent 通过 **Long Polling** 支持 Telegram 集成，无需公网 IP 或 ngrok。

### 配置步骤

1. 在 [@BotFather](https://t.me/BotFather) 创建 Bot 并获取 token
2. 在 `.env` 中添加：
   ```env
   TELEGRAM_BOT_TOKEN=你的token
   TELEGRAM_POLLING_ENABLED=true
   ```
3. 重启服务（Docker 或本地运行）

当 `TELEGRAM_POLLING_ENABLED=true` 时，Bot 会开始轮询消息。每个 Telegram 用户享受独立会话（`tg_<chat_id>`），支持多轮对话。



### 注意事项

- 非文本消息（图片、贴纸等）会被静默忽略
- 超长消息会自动分段（Telegram 单条消息上限 4096 字符）
- 保留 `/webhook/telegram` 端点作为 Webhook 模式的后备方案（需 ngrok）

## Provider

Provider preset 统一放在 `app/config.yaml`。前端从 `/meta` 获取 provider 列表并渲染下拉框，用户选择会保存到 `localStorage`。选择 provider 后使用其 `default_model`；高级模型覆盖仍可通过 `LLM_MODEL_ID` 或 API 参数传入。

| Provider | 默认模型 | 说明 |
|----------|----------|------|
| DeepSeek | `deepseek-chat` | 使用 `DEEPSEEK_API_KEY` |
| Kilo | `kilo-auto/free` | 使用 `KILO_API_KEY` |
| Ollama | `qwen3:8b` | 本地 OpenAI-compatible endpoint，无需 API Key |
| Custom | 手动配置 | 通常使用 `LLM_API_KEY` 和 `LLM_BASE_URL` |

## 项目结构

```
app/
├── agent.py          # Tool Call 主循环与 SSE 事件编排
├── compression.py    # CompressionMixin：L1/L2 压缩与兜底摘要
├── subagent_runner.py # 父 Agent 侧 run_subagent 线程/队列事件转发
├── prompt_loader.py  # Markdown prompt 加载与渲染
├── llm/              # LLM 客户端封装层
│   ├── client.py     # OpenAI-compatible adapter
│   ├── provider_config.py # 从 config.yaml + .env 解析 provider
│   └── types.py      # LLMResponse / ToolCall / Usage DTO
├── registry.py       # 工具注册表、schema 与 dispatch 辅助
├── session_manager.py # 会话持久化管理
├── todo_manager.py # Todo 状态管理
├── server.py      # FastAPI 服务
├── channel/       # 消息平台接入
│   ├── __init__.py
│   └── telegram.py
├── tools/        # 工具实现
│   ├── read_file.py
│   ├── write_file.py
│   ├── edit_file.py
│   ├── bash.py
│   ├── web_fetch.py
│   ├── websearch.py      # Tavily 联网搜索
│   ├── summarize.py      # 摘要 transcript 格式化辅助
│   ├── install_skill.py  # ClawHub Skill 安装
│   ├── compact.py        # 主动触发上下文压缩
│   ├── current_time.py   # 当前时间
│   ├── system_info.py    # 容器系统信息
│   ├── subagent.py       # 子 Agent 隔离派发
│   └── todo.py
├── prompts/       # Prompt 模板
│   ├── system.md
│   ├── subagent_system.md
│   ├── subagent_summary.md
│   ├── compression_summary.md
│   ├── compression_summary_fallback.md
│   └── compression_subagent_hint.md
└── static/       # Vue 前端
    └── index.html
```

## 使用方式

1. 在左侧输入框描述任务
2. Agent 会自动规划并执行多步骤操作
3. 每一步的 Thought/Action/Observation 实时展示
4. 右侧面板显示任务进度

## 内置工具

| 工具 | 说明 |
|------|------|
| `bash` | 在容器内执行 shell 命令，30 秒超时，输出自动截断 |
| `read` / `write_file` / `edit` | 在 `workspace/` 沙箱内读取、写入和局部替换文件 |
| `web_fetch` | 获取指定 URL 内容，HTML 自动提取文本 |
| `websearch` | 使用 Tavily Search API 联网搜索，支持 `max_results`、`search_depth`、`topic`、`time_range`、域名 include/exclude、`include_answer` |
| `todo_add` / `todo_update` / `todo_replan` | 管理多步骤任务状态 |
| `run_subagent` | 将独立调研、分析、批处理、报告类任务交给子 Agent；支持单任务或批量并发 |
| `install_skill` | 从 ClawHub 或 GitHub 安装 Skill 到 `workspace/skills/` |
| `compact` | 主动触发上下文压缩 |
| `get_current_time` / `get_system_info` / `get_token_usage` | 查询运行时状态 |

## 测试

`tests/test_state_flow.py` 和 `tests/test_subagent_stability.py` 覆盖上下文压缩不变量、子 Agent task/tool 运行中事件、父 Agent SSE 转发、刷新恢复，以及 `SUBAGENT_LLM_*` 优先于父 Agent provider/model 的配置逻辑。

```bash
python3 -m unittest tests/test_state_flow.py tests/test_subagent_stability.py
```

## 许可证

MIT
