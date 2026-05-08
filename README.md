# NanoAgent v0.8

A minimal ReAct Agent implementation with LLM client, tool registry, web UI, Telegram Bot integration, and ClawHub Skill system.

> [简体中文](./README_zh.md)

## Features

- **Tool Call Loop**: Native tool calling based on OpenAI Tool Call protocol
- **Provider-Based LLM Support**: OpenAI-compatible providers configured in `app/config.yaml` (DeepSeek, Kilo, Ollama, custom)
- **Tool System**: Auto-registered tools with `@tool` decorator
- **ClawHub Skill System**: `install_skill` tool for automated skill installation from ClawHub
- **Todo Management**: Multi-step task planning and tracking
- **Session Persistence**: Independent session storage with automatic saving to JSON files
- **Web UI**: FastAPI backend + Vue 3 frontend with stream output
- **Markov Streaming**: Real-time token-by-token output
- **Telegram Bot**: Long Polling integration—send messages to Bot, get Agent responses directly in Telegram (no ngrok required)
- **Context Compression**: Automatic context summarization for extended conversations, prevents token limit overflow
- **Context-Aware Compaction Anchors**: Compacted history preserves the system prompt, initial user request, latest user request, and authoritative task status
- **Independent Summary Model**: Context summaries can use `SUMMARY_LLM_*` (for example local Ollama) independently from the chat provider
- **Reliable Summary Fallback**: LLM summaries record finish reasons, retry on truncated output, and preserve prior summaries when falling back locally
- **Split UI History / LLM Context**: Refresh shows the full display history while only the model-facing context is compacted
- **Token Usage Tracking**: Per-answer token usage is persisted, while session lists show current context-window usage separately from lifetime token spend

## Context and Token Handling

NanoAgent separates three related but different token concepts:

- **Per-answer usage**: Stored on assistant messages as `usage`, so answer cards keep their input/output token counts after refresh or session switching.
- **Current context usage**: Stored as `context_usage`, representing the latest prompt/window footprint shown as `ctx current / model context length` in the session list.
- **Lifetime usage**: Stored as `token_usage`, representing cumulative tokens spent by the whole session. This can exceed the model context length and is shown as supporting metadata rather than the active window size.

When context is compacted, NanoAgent keeps stable anchors instead of replacing everything with a single summary: system prompt, first user request, compacted summary, current todo/task status, and latest user request. The persisted UI history remains separate from the compacted LLM context, so refresh can still show the original conversation.

## Quick Start

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 2. Run with Docker
docker compose up -d

# 3. Open browser
http://localhost:9090
```

## Windows Setup with Docker

1. **Install Docker Desktop**:
   - Download from [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
   - Install and start Docker Desktop
   - Ensure WSL2 is enabled (recommended for better performance)

2. **Run the service**:
   ```cmd
   cd C:\path\to\NanoAgent
   docker-compose up --build
   ```

3. **Access the web UI**:
   - Open browser to `http://localhost:9090`

**Note**: Ensure port 9090 is available. Docker Desktop provides a complete containerized environment for development and deployment.

## Environment Variables

| Variable | Description |
|----------|------------|
| `LLM_PROVIDER` | Default chat provider (`deepseek`, `kilo`, `ollama`, or `custom`) |
| `LLM_MODEL_ID` | Optional chat model override; empty uses the provider preset in `app/config.yaml` |
| `LLM_API_KEY` | Generic OpenAI-compatible API key fallback |
| `LLM_BASE_URL` | Optional explicit OpenAI-compatible endpoint override |
| `DEEPSEEK_API_KEY` | DeepSeek provider API key |
| `KILO_API_KEY` | Kilo provider API key |
| `SUMMARY_LLM_PROVIDER` | Optional summary provider; empty reuses the default chat provider |
| `SUMMARY_LLM_API_KEY` | Optional summary API key |
| `SUMMARY_LLM_BASE_URL` | Optional summary endpoint override, useful for local Ollama from Docker |
| `SUMMARY_LLM_MODEL_ID` | Optional summary model override |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token from @BotFather (optional) |
| `TELEGRAM_POLLING_ENABLED` | Set to `true` to enable Telegram Long Polling |

## Configuration

Agent behavior can be customized via `app/config.yaml`:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `default.provider` | Default chat provider shown on first load | deepseek |
| `providers.<name>.base_url` | Provider OpenAI-compatible endpoint preset | varies |
| `providers.<name>.default_model` | Provider default model when no override is supplied | varies |
| `providers.<name>.api_key_env` | Environment variable name for this provider's API key | varies |
| `agent.max_steps` | Maximum reasoning steps per query | 200 |
| `agent.temperature` | LLM temperature (creativity vs consistency) | 0.1 |
| `agent.max_tokens` | Max output tokens per LLM call | 16384 |
| `agent.nag_threshold` | Rounds without todo tool before reminder injection | 3 |
| `compression.enabled` | Toggle automatic context compression | true |
| `compression.layer1.keep_recent_tool_messages` | Keep the latest N tool results uncompressed | 3 |
| `compression.layer1.content_threshold` | Compress older tool results above this character length | 200 |
| `compression.layer2.token_threshold` | Trigger L2 summary compaction above this estimated token count | 5000 |
| `compression.layer2.message_threshold` | Trigger L2 summary compaction above this message count | 100 |
| `compression.layer2.summary.max_tokens` | Normal LLM summary output budget | 1200 |
| `compression.layer2.summary.retry_max_tokens` | Retry budget when a summary is truncated | 2400 |
| `compression.layer2.summary.max_chars` | Max stored summary characters after parsing | 1200 |

**Example config.yaml:**
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
    default_model: "qwen2.5:7b"
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
    token_threshold: 5000
    message_threshold: 100
    summary:
      temperature: 0.1
      max_tokens: 1200
      retry_max_tokens: 2400
      max_chars: 1200
```

## Telegram Bot

NanoAgent supports Telegram integration via **Long Polling**—no public IP or ngrok required.

### Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) and get your token
2. Add the token to your `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=your:token
   TELEGRAM_POLLING_ENABLED=true
   ```
3. Restart the service (Docker or local)

When `TELEGRAM_POLLING_ENABLED=true`, the bot starts polling Telegram for messages. Each Telegram user gets an independent session (`tg_<chat_id>`), so multi-turn conversations work out of the box.

### Usage

- Open Telegram and send any text message to your bot
- Bot replies with `⏳ 处理中...` immediately
- Agent processes the request and sends back the final answer

### Notes

- Non-text messages (photos, stickers, etc.) are silently ignored
- Long messages are automatically split (Telegram limit: 4096 chars per message)
- The `/webhook/telegram` endpoint remains available as a fallback (requires ngrok) if you prefer Webhook mode

## Providers

Provider presets live in `app/config.yaml`. The web UI renders the provider list from this config and stores the selected provider in `localStorage`. Selecting a provider uses its `default_model`; advanced model overrides can still be supplied through `LLM_MODEL_ID` or API parameters.

| Provider | Default Model | Notes |
|----------|---------------|-------|
| DeepSeek | `deepseek-chat` | Uses `DEEPSEEK_API_KEY` |
| Kilo | `kilo-auto/free` | Uses `KILO_API_KEY` |
| Ollama | `qwen2.5:7b` | Local OpenAI-compatible endpoint; no API key required |
| Custom | configured manually | Uses `LLM_API_KEY` and usually `LLM_BASE_URL` |

## Architecture

```
app/
├── agent.py          # Tool Call loop implementation
├── llm/              # LLM client layer
│   ├── client.py     # OpenAI-compatible adapter
│   ├── provider_config.py # Provider resolver from config.yaml + .env
│   └── types.py      # LLMResponse / ToolCall / Usage DTOs
├── registry.py       # Tool registry
├── session_manager.py # Session persistence management
├── todo_manager.py # Todo state management
├── server.py      # FastAPI server
├── channel/       # Messaging platform integrations
│   ├── __init__.py
│   └── telegram.py
├── tools/        # Tool implementations
│   ├── read_file.py
│   ├── write_file.py
│   ├── edit_file.py
│   ├── bash.py
│   ├── web_fetch.py
│   ├── summarize.py      # Context compression utilities
│   ├── install_skill.py  # ClawHub Skill installation
│   └── todo.py
├── prompts/       # Prompt templates
│   └── system.md
└── static/       # Vue frontend
    └── index.html
```

## License

MIT
