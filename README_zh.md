# NanoAgent v0.2

一个最小化的 ReAct Agent 实现，支持 LLM 调用、工具注册和 Web UI。

> [English](./README.md)

## 功能特性

- **Tool Call 循环**：基于 OpenAI Tool Call 协议的原生工具调用
- **多模型支持**：DeepSeek (Chat/Reasoner)、Kilo (GPT-4o、Claude 等)
- **工具系统**：基于 `@tool` 装饰器自动注册
- **任务管理**：多步骤任务规划与状态跟踪
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

## 环境变量

| 变量 | 说明 |
|------|------|
| `LLM_API_KEY` | Kilo API Key |
| `LLM_BASE_URL` | Kilo Gateway URL |
| `LLM_MODEL_ID` | 模型 ID（如 `kilo-auto/free`） |
| `DEEPSEEK_API_KEY` | DeepSeek API Key（可选） |

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