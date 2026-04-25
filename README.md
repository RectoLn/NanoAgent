# NanoAgent v0.7

A minimal ReAct Agent implementation with LLM client, tool registry, web UI, Telegram Bot integration, and ClawHub Skill system.

> [简体中文](./README_zh.md)

## Features

- **Tool Call Loop**: Native tool calling based on OpenAI Tool Call protocol
- **Multi-Provider LLM Support**: DeepSeek (Chat/Reasoner), Kilo (GPT-4o, Claude, etc.)
- **Tool System**: Auto-registered tools with `@tool` decorator
- **ClawHub Skill System**: `install_skill` tool for automated skill installation from ClawHub
- **Todo Management**: Multi-step task planning and tracking
- **Session Persistence**: Independent session storage with automatic saving to JSON files
- **Web UI**: FastAPI backend + Vue 3 frontend with stream output
- **Markov Streaming**: Real-time token-by-token output
- **Telegram Bot**: Long Polling integration—send messages to Bot, get Agent responses directly in Telegram (no ngrok required)
- **Context Compression**: Automatic context summarization for extended conversations, prevents token limit overflow

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
| `LLM_API_KEY` | Kilo API Key |
| `LLM_BASE_URL` | Kilo Gateway URL |
| `LLM_MODEL_ID` | Model ID (e.g., `kilo-auto/free`) |
| `DEEPSEEK_API_KEY` | DeepSeek API Key (optional) |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token from @BotFather (optional) |

## Configuration

Agent behavior can be customized via `app/config.yaml`:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `agent.max_steps` | Maximum reasoning steps per query | 200 |
| `agent.temperature` | LLM temperature (creativity vs consistency) | 0.1 |
| `agent.max_tokens` | Max output tokens per LLM call | 16384 |
| `agent.nag_threshold` | Rounds without todo tool before reminder injection | 3 |
| `context.compress_threshold_tokens` | Trigger compression when non-system messages exceed N words | 6000 |
| `context.compress_threshold_messages` | Trigger compression when non-system messages exceed N | 30 |
| `context.keep_recent_messages` | Always preserve the N most recent messages (not compressed) | 10 |
| `context.compression_enabled` | Toggle automatic context compression (false for debugging) | true |

**Example config.yaml:**
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

NanoAgent supports Telegram integration via **Long Polling**—no public IP or ngrok required.

### Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) and get your token
2. Add the token to your `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=your:token
   ```
3. Restart the service (Docker or local)

The bot will automatically start polling Telegram for messages. Each Telegram user gets an independent session (`tg_<chat_id>`), so multi-turn conversations work out of the box.

### Usage

- Open Telegram and send any text message to your bot
- Bot replies with `⏳ 处理中...` immediately
- Agent processes the request and sends back the final answer

### Notes

- Non-text messages (photos, stickers, etc.) are silently ignored
- Long messages are automatically split (Telegram limit: 4096 chars per message)
- The `/webhook/telegram` endpoint remains available as a fallback (requires ngrok) if you prefer Webhook mode

## Available Models

| Provider | Model | Description |
|----------|-------|-------------|
| DeepSeek | `deepseek-chat` | V3 Chat |
| DeepSeek | `deepseek-reasoner` | R1 Reasoner |
| Kilo | `kilo-auto/free` | Auto select free model |
| Kilo | `anthropic/claude-3-5-sonnet` | Claude 3.5 |
| Kilo | `openai/gpt-4o` | GPT-4o |

## Architecture

```
app/
├── agent.py          # Tool Call loop implementation
├── client.py        # LLM client (OpenAI compatible)
├── registry.py     # Tool registry
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