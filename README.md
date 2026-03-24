# LiveAudio Airbnb Assistant

A terminal-based AI travel assistant that collects a few trip inputs, runs parallel research agents, and produces both structured JSON and a styled self-contained HTML travel brief.

The current pipeline covers:
- Airbnb stays
- Neighborhood summary
- Weather
- Activities
- Food picks
- Commute planning
- Flights, using direct `fast-flights` integration with local Playwright

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with MCP Toolkit enabled
- A MiniMax API key
- A Brave Search API key
- A Google Maps API key

Docker MCP is still used for Airbnb, Brave Search, and OpenWeather. Flights no longer use Docker MCP.

## Setup

```bash
uv sync
cp .env.example .env
```

Fill in `.env` with at least:
- `MINIMAX_API_KEY`
- `BRAVE_API_KEY`
- `GOOGLE_MAPS_API_KEY`

Install the local browser runtime used by flight search:

```bash
uv run python -m playwright install chromium
```

## Run

```bash
uv run python main.py
```

The app writes JSON and HTML outputs to `output/`.

## Stack

| Component | Technology |
|-----------|------------|
| Language | Python |
| Package manager | uv |
| Agent framework | PydanticAI |
| Model provider | MiniMax M2.7 via Anthropic-compatible API |
| MCP-backed tools | Airbnb, Brave Search, OpenWeather, Google Maps |
| Direct Python flight search | `fast-flights[local]` + Playwright |
