# LiveAudio Airbnb Assistant

A terminal-first travel research pipeline that collects one trip brief, runs specialized research agents, and outputs:

- structured JSON
- a self-contained HTML travel book
- direct links for actionable recommendations

The current pipeline covers:

- Airbnb stays with deterministic image scraping
- neighborhood summary
- weather and packing guidance
- activities with `source_url` and best-effort metadata image enrichment
- food picks with `source_url` and best-effort metadata image enrichment
- optional flights via direct `fast-flights` + local Playwright

## How It Works

Input can come from:

- interactive terminal prompts
- a saved JSON scenario file

The pipeline then:

1. validates intake into `IntakeOutput`
2. runs research agents for stays, neighborhood, activities, food, weather, and optional flights
3. normalizes and enriches activity/food source links and images
4. curates the final `CurationOutput`
5. builds a deterministic presentation deck spec, selects a curated style preset, and renders a self-contained HTML travel book

Notes:

- Flights are optional and run only when `origin_airport` is provided.
- Activity and food cards now expose `source_url` so users can click through in both JSON and HTML.
- Partial failures degrade gracefully and write debug artifacts to `output/debug/`.

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with MCP Toolkit enabled
- `MINIMAX_API_KEY`
- `TAVILY_API_KEY`

Runtime integrations:

- MCP: Airbnb, Tavily, OpenWeather
- Direct Python tooling: `fast-flights[local]` + Playwright

## Setup

```bash
uv sync
cp .env.example .env
```

Fill in `.env` with at least:

- `MINIMAX_API_KEY`
- `TAVILY_API_KEY`

Install the local browser runtime used by flight search:

```bash
uv run python -m playwright install chromium
```

## Run

Interactive:

```bash
uv run python main.py
```

From a saved scenario:

```bash
uv run python main.py --input docs/scenarios/lisbon_workcation_roundtrip.json
```

Outputs are written to `output/`:

- `*.json` travel brief
- `*.html` travel book
- `output/debug/*.log` for failed agent runs

## Validation

Run the current unit suite with:

```bash
uv run python -m unittest discover -s tests -v
```

## Scenario Fixtures

The repo includes reusable end-to-end scenario files:

- `docs/scenarios/lisbon_workcation_roundtrip.json`
- `docs/scenarios/barcelona_business_roundtrip.json`
- `docs/scenarios/istanbul_workcation_roundtrip.json`
- `docs/scenarios/denver_business_roundtrip.json`
- `docs/scenarios/sydney_workcation_roundtrip.json`
- `docs/scenarios/kyoto_romantic_roundtrip.json`
- `docs/scenarios/marrakech_weekend_getaway_roundtrip.json`
- `docs/scenarios/mexico_city_event_based_roundtrip.json`
- `docs/scenarios/cape_town_family_roundtrip.json`
- `docs/scenarios/buenos_aires_vacation_roundtrip.json`

These are intended for repeatable regression runs without re-entering intake prompts.

## Useful Docs

- `docs/SCENARIO_RUNBOOK.md` — how to run and interpret scenario tests
- `docs/DOCS.md` — maintainer doc map and external references
- `docs/REQUIREMENTS.md` — current runtime expectations and constraints
- `docs/TAVILY_WORKFLOW.md` — how Tavily is used at runtime vs maintainer workflows
- `scripts/debug_agent.py` — run one research agent in isolation against a scenario file

## Stack

| Component | Technology |
|-----------|------------|
| Language | Python |
| Package manager | uv |
| Agent framework | PydanticAI |
| Model provider | MiniMax M2.7 via Anthropic-compatible API |
| MCP-backed tools | Airbnb, Tavily, OpenWeather |
| Direct Python flight search | `fast-flights[local]` + Playwright |
| HTML generation | Deterministic presentation system (`DeckSpec` + style presets + HTML renderer) |
