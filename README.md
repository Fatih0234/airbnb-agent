# Airbnb Stay-Matching Copilot

A terminal-based AI agent that helps you find Airbnb stays through conversation.

Built with Python, PydanticAI, OpenRouter, and Docker MCP Toolkit.

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with MCP Toolkit enabled
- [OpenRouter API key](https://openrouter.ai/keys)

## Setup

```bash
uv sync
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY
```

## Run

```bash
uv run python main.py
```

## Example

```
You: Find me a place in Amsterdam for 2 guests next weekend
You: Show me more details about the first result
You: What's the cheapest option?
```

## Stack

| Component | Technology |
|-----------|------------|
| Language | Python |
| Package manager | uv |
| Agent framework | PydanticAI |
| Model provider | OpenRouter (minimax/minimax-m2.7) |
| Tool server | Docker MCP Toolkit (Airbnb MCP) |
