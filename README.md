# NanoAgent v0.1

A minimal ReAct Agent implementation with LLM client, tool registry, and web UI.

## Features

- **ReAct Loop**: Thought → Action → Observation cycle
- **Multi-Provider LLM Support**: DeepSeek (Chat/Reasoner), Kilo (GPT-4o, Claude, etc.)
- **Tool System**: Auto-registered tools with `@tool` decorator
- **Todo Management**: Multi-step task planning and tracking
- **Web UI**: FastAPI backend + Vue 3 frontend with stream output
- **Markov Streaming**: Real-time token-by-token output

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

## Environment Variables

| Variable | Description |
|----------|------------|
| `LLM_API_KEY` | Kilo API Key |
| `LLM_BASE_URL` | Kilo Gateway URL |
| `LLM_MODEL_ID` | Model ID (e.g., `kilo-auto/free`) |
| `DEEPSEEK_API_KEY` | DeepSeek API Key (optional) |

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
├── agent.py          # ReAct loop implementation
├── client.py        # LLM client (OpenAI compatible)
├── registry.py     # Tool registry
├── todo_manager.py # Todo state management
├── server.py      # FastAPI server
├── tools/        # Tool implementations
│   ├── read_file.py
│   ├── write_file.py
│   ├── edit_file.py
│   ├── bash.py
│   └── todo.py
├── prompts/       # Prompt templates
│   └── system.md
└── static/       # Vue frontend
    └── index.html
```

## License

MIT