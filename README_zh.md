# NanoAgent v0.3

一个最小化的 ReAct Agent 实现，支持 LLM 调用、工具注册和 Web UI。

> [English](./README.md)

## 功能特性

- **Tool Call 循环**：基于 OpenAI Tool Call 协议的原生工具调用
- **多模型支持**：DeepSeek (Chat/Reasoner)、Kilo (GPT-4o、Claude 等)
- **工具系统**：基于 `@tool` 装饰器自动注册
- **任务管理**：多步骤任务规划与状态跟踪
- **会话持久化**：独立会话存储，自动保存到 JSON 文件
- **Web UI**：FastAPI 后端 + Vue 3 前端，流式输出
- **实时流式**：逐 token 实时输出

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
   docker-compose up
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

## 配置选项

Agent 行为可以通过 `app/config.yaml` 自定义：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `agent.max_steps` | 每次查询的最大推理步骤 | 50 |
| `agent.temperature` | LLM 温度参数（创造性 vs 一致性） | 0.1 |
| `agent.nag_threshold` | 未调用 todo 工具的连续轮数阈值（注入提醒） | 3 |

**config.yaml 示例：**
```yaml
agent:
  max_steps: 50
  temperature: 0.1
  nag_threshold: 3
```

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
├── tools/        # 工具实现
│   ├── read_file.py
│   ├── write_file.py
│   ├── edit_file.py
│   ├── bash.py
│   ├── web_fetch.py
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