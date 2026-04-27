# NanoAgent v0.8

一个最小化的 ReAct Agent 实现，支持 LLM 调用、工具注册、Web UI、Telegram Bot 集成，以及 ClawHub Skill 技能系统。

> [English](./README.md)

## 功能特性

- **Tool Call 循环**：基于 OpenAI Tool Call 协议的原生工具调用
- **多模型支持**：DeepSeek (Chat/Reasoner)、Kilo (GPT-4o、Claude 等)
- **工具系统**：基于 `@tool` 装饰器自动注册
- **ClawHub Skill 技能系统**：内置 `install_skill` 工具，支持从 ClawHub 自动安装技能
- **任务管理**：多步骤任务规划与状态跟踪
- **会话持久化**：独立会话存储，自动保存到 JSON 文件
- **Web UI**：FastAPI 后端 + Vue 3 前端，流式输出
- **实时流式**：逐 token 实时输出
- **Telegram Bot**：基于 Long Polling 的消息平台集成（无需公网地址），在 Telegram 中直接与 Agent 对话
- **上下文压缩**：自动压缩长对话历史为智能摘要，防止 token 溢出，压缩记录内置存储于会话文件
- **上下文压缩锚点**：压缩后保留 system prompt、初始用户输入、最新用户输入，以及当前权威 Todo/任务状态。
- **Token 统计持久化**：回答卡片保存本轮 usage，刷新或切换会话后仍可恢复；会话列表区分当前上下文窗口占用和会话累计消耗。

## 上下文与 Token 统计

NanoAgent 将三个容易混淆的 token 指标拆开处理：

- **单轮回答 usage**：写入 assistant message 的 `usage` 字段，用于恢复回答卡片上的输入/输出 token。
- **当前上下文窗口**：写入 session 的 `context_usage` 字段，表示最近一次请求的 prompt/window 占用，前端显示为 `ctx 当前 / 模型窗口`。
- **会话累计消耗**：写入 session 的 `token_usage` 字段，表示整个会话累计花费，可超过模型窗口，只作为成本/历史统计。

上下文压缩不会只留下单条摘要，而是保留稳定锚点：system prompt、第一条用户请求、压缩摘要、当前 Todo/任务状态、最新用户请求。

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

## 环境变量

| 变量 | 说明 |
|------|------|
| `LLM_API_KEY` | Kilo API Key |
| `LLM_BASE_URL` | Kilo Gateway URL |
| `LLM_MODEL_ID` | 模型 ID（如 `kilo-auto/free`） |
| `DEEPSEEK_API_KEY` | DeepSeek API Key（可选） |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token（由 @BotFather 创建） |

## 配置选项

Agent 行为可以通过 `app/config.yaml` 自定义：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `agent.max_steps` | 每次查询的最大推理步骤 | 200 |
| `agent.temperature` | LLM 温度参数（创造性 vs 一致性） | 0.1 |
| `agent.max_tokens` | 每次 LLM 调用的最大输出 token 数 | 16384 |
| `agent.nag_threshold` | 未调用 todo 工具的连续轮数阈值（注入提醒） | 3 |
| `context.compress_threshold_tokens` | 触发压缩的词数阈值（非 system 消息） | 6000 |
| `context.compress_threshold_messages` | 触发压缩的消息数阈值（非 system 消息） | 30 |
| `context.keep_recent_messages` | 每次压缩保留的最近消息数（不压缩） | 10 |
| `context.compression_enabled` | 启用/禁用自动压缩（false 用于调试） | true |

**config.yaml 示例：**
```yaml
agent:
  max_steps: 200
  temperature: 0.1
  max_tokens: 16384
  nag_threshold: 3

context:
  compress_threshold_tokens: 6000
  compress_threshold_messages: 30
  keep_recent_messages: 10
  compression_enabled: true
```

## Telegram Bot

NanoAgent 通过 **Long Polling** 支持 Telegram 集成，无需公网 IP 或 ngrok。

### 配置步骤

1. 在 [@BotFather](https://t.me/BotFather) 创建 Bot 并获取 token
2. 在 `.env` 中添加：
   ```env
   TELEGRAM_BOT_TOKEN=你的token
   ```
3. 重启服务（Docker 或本地运行）

Bot 会自动开始轮询消息。每个 Telegram 用户享受独立会话（`tg_<chat_id>`），支持多轮对话。

### 使用方式

- 在 Telegram 中向 Bot 发送任意文本消息
- Bot 先回复 `⏳ 处理中...`
- Agent 处理完成后返回最终答案

### 注意事项

- 非文本消息（图片、贴纸等）会被静默忽略
- 超长消息会自动分段（Telegram 单条消息上限 4096 字符）
- 保留 `/webhook/telegram` 端点作为 Webhook 模式的后备方案（需 ngrok）

## 可用模型

| 提供商 | 模型 | 说明 |
|--------|------|------|
| DeepSeek | `deepseek-chat` | V3 对话模型 |
| DeepSeek | `deepseek-reasoner` | R1 推理模型 |
| Kilo | `kilo-auto/free` | 自动选择免费模型 |
| Kilo | `anthropic/claude-3-5-sonnet` | Claude 3.5 |
| Kilo | `openai/gpt-4o` | GPT-4o |

## 项目结构

```
app/
├── agent.py          # Tool Call 循环实现
├── client.py        # LLM 客户端（OpenAI 兼容）
├── registry.py     # 工具注册表
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
│   ├── summarize.py      # 上下文压缩工具
│   ├── install_skill.py  # ClawHub Skill 安装
│   └── todo.py
├── prompts/       # Prompt 模板
│   └── system.md
└── static/       # Vue 前端
    └── index.html
```

## 使用方式

1. 在左侧输入框描述任务
2. Agent 会自动规划并执行多步骤操作
3. 每一步的 Thought/Action/Observation 实时展示
4. 右侧面板显示任务进度

## 许可证

MIT
