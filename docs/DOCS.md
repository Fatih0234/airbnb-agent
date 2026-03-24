# DOCS.md

Maintainer doc map for the current runtime, not the original build plan.

## Read These First

1. `README.md`
2. `REQUIREMENTS.md`
3. `SCENARIO_RUNBOOK.md`
4. this file

## Current Architecture Truth

The repo currently runs a terminal-first batch pipeline:

1. collect or load `IntakeOutput`
2. run research agents for stays, neighborhood, activities, food, weather, commute, and optional flights
3. normalize activity/food outputs and enrich them with deterministic metadata image scraping from `source_url`
4. curate the final `CurationOutput`
5. render deterministic HTML and save JSON/HTML to `output/`

Important current facts:

- Curation is deterministic Python, not an LLM stage.
- HTML generation is deterministic Python, not a slide-generation skill.
- Flights use direct Python tools in `app/flight_search.py`, not MCP.
- Stay images are scraped directly from Airbnb listing pages.
- Activity and food images are best-effort metadata extracts from `source_url`.
- Search-backed agent runs are serialized through `app/search_agent.py` to reduce rate-limit failures.

## Repo Files That Matter

- `app/pipeline.py` — orchestration, retries, degradation, output persistence
- `app/schemas.py` — canonical I/O contract
- `app/content_enrichment.py` — activity/food source normalization and image extraction
- `app/airbnb_images.py` — stay image scraping
- `app/mcp_client.py` — MCP process factories
- `app/flight_search.py` — direct flight search helpers
- `app/agents/` — research agents, curation, and HTML rendering
- `scripts/debug_agent.py` — run one research agent in isolation against a scenario file

## External Docs

### PydanticAI

- Overview: https://ai.pydantic.dev/
- Agents: https://ai.pydantic.dev/agents/
- Toolsets: https://ai.pydantic.dev/toolsets/
- MCP overview: https://ai.pydantic.dev/mcp/overview/
- Structured output: https://ai.pydantic.dev/output/
- Anthropic models: https://ai.pydantic.dev/models/anthropic/

### MiniMax

- Anthropic-compatible API: https://platform.minimax.io/docs/api-reference/text-anthropic-api
- Base URL: `https://api.minimax.io/anthropic`

### Airbnb MCP

- Overview: https://hub.docker.com/mcp/server/openbnb-airbnb/overview
- Tools: https://hub.docker.com/mcp/server/openbnb-airbnb/tools
- Repo: https://github.com/openbnb-org/mcp-server-airbnb

Current usage:

- `airbnb_search`
- `ignoreRobotsText: true`

### Tavily MCP

- Docs: https://docs.tavily.com/documentation/mcp
- Repo: https://github.com/tavily-ai/tavily-mcp

Current usage:

- `tavily-search` for research and airport-code lookup
- `tavily-extract` only as a limited follow-up option in activities/food
- default params: advanced search, `max_results=8`, `include_images=false`, `include_raw_content=false`

### Google Maps MCP

- Repo: https://github.com/cablate/mcp-google-map

Current usage:

- geocoding
- commute directions and distance matrix
- static map generation

### OpenWeather MCP

- Run via Docker MCP gateway
- Used only by the weather agent

### fast-flights

- Repo: https://github.com/AWeirdDev/flights
- Docs: https://aweirddev.github.io/flights/
- Local Playwright mode: https://aweirddev.github.io/flights/local.html

## What To Check When Debugging

- `output/debug/*.log` for agent failures after retries
- `scripts/debug_agent.py` for isolated reruns
- scenario fixtures in `docs/scenarios/`
- `SCENARIO_RUNBOOK.md` for regression expectations

Known recurring issues:

- some activity/food source pages return `403` or `404`, which reduces image fill but should not fail the run
- concurrent runs can push flights into request-limit failures
- some Google Maps place-type requests can fail on unsupported categories

## Practical Guidance

- Keep docs focused on the current runtime, not historical architecture proposals.
- Prefer deterministic post-processing when possible instead of asking the model to invent fields.
- Treat `source_url` as user-facing contract data for activities and food.
- Prefer official docs and primary tool repos when updating integrations.
