# DOCS.md

This file lists the main documentation the coding agent should use while building the pipeline.

## Read these first
1. `PRD.md`
2. `REQUIREMENTS.md`
3. this `DOCS.md`

---

## Main stack docs

### PydanticAI
Use these as the main implementation docs:
- Overview: https://ai.pydantic.dev/
- Agent docs: https://ai.pydantic.dev/agents/
- Dependencies: https://ai.pydantic.dev/dependencies/
- Tools: https://ai.pydantic.dev/tools/
- Toolsets: https://ai.pydantic.dev/toolsets/
- Built-in tools: https://ai.pydantic.dev/builtin-tools/
- MCP overview: https://ai.pydantic.dev/mcp/overview/
- Output and structured output: https://ai.pydantic.dev/output/
- Messages and history: https://ai.pydantic.dev/message-history/
- **Multi-agent applications: https://ai.pydantic.dev/multi-agent-applications/** ← new, required for Phase 2

### MiniMax (LLM provider)
All agents use MiniMax M2.7 via the Anthropic-compatible API:
- API reference: https://platform.minimax.io/docs/api-reference/text-anthropic-api
- Base URL: `https://api.minimax.io/anthropic`
- Auth: `MINIMAX_API_KEY` env var
- pydantic-ai integration: `AnthropicModel` + `AnthropicProvider(anthropic_client=AsyncAnthropic(base_url=..., api_key=...))`
- pydantic-ai Anthropic docs: https://ai.pydantic.dev/models/anthropic/

Models in use:
- All agents (research + synthesis): `MiniMax-M2.7`

### Airbnb MCP
- Docker Hub overview: https://hub.docker.com/mcp/server/openbnb-airbnb/overview
- Docker Hub tools: https://hub.docker.com/mcp/server/openbnb-airbnb/tools
- GitHub repo: https://github.com/openbnb-org/mcp-server-airbnb
- Run via: `docker mcp gateway run --servers openbnb-airbnb`
- Tools used: `airbnb_search`, `airbnb_listing_details`
- Note: always set `ignoreRobotsText: true`

### Brave Search MCP
- Docker Hub: https://hub.docker.com/r/mcp/brave-search
- Run via: `docker mcp gateway run --servers brave-search`
- Tools used:
  - `brave_web_search` — general web research, neighborhood safety
  - `brave_local_search` — nearby businesses, restaurants, POIs
  - `brave_llm_context_search` — pre-extracted content optimized for LLM grounding
  - `brave_news_search` — recent events about a location
  - `brave_image_search` — location/food/activity images

### Google Maps MCP
- GitHub repo: https://github.com/cablate/mcp-google-map
- Run via: `npx @cablate/mcp-google-map --stdio` (note: npx, not Docker)
- Requires: `GOOGLE_MAPS_API_KEY` env var (Google Cloud: Places API New, Routes API, Maps API)
- Tools used:
  - `maps_directions` (mode: transit) — step-by-step transit commute with travel time
  - `maps_distance_matrix` — travel times to multiple destinations at once
  - `maps_search_nearby` — find places by type near a location
  - `maps_place_details` — full place info including photos
  - `maps_static_map` — generates map image with markers/routes for embedding in slides
  - `maps_explore_area` — neighborhood overview in a single call
  - `maps_plan_route` — multi-stop itinerary up to 25 waypoints

### OpenWeather MCP
- Run via: `docker mcp gateway run --servers openweather`
- Used by: Weather Agent
- Returns: forecast for travel dates, conditions, seasonal context

### fast-flights
- Repo: https://github.com/AWeirdDev/flights
- Docs: https://aweirddev.github.io/flights/
- Local Playwright mode: https://aweirddev.github.io/flights/local.html
- Used by: Flights Agent
- Integration style: direct Python tools via `FunctionToolset`, not MCP
- Current fetch mode: `fetch_mode="local"` to avoid consent-page failures from the old Docker wrapper

### Tenacity (retry library)
- Docs: https://tenacity.readthedocs.io/en/latest/
- Use for: wrapping agent runs and tool calls with retry + backoff logic
- Use when: PydanticAI does not natively cover the retry scenario needed

### frontend-slides skill
- GitHub: https://github.com/zarazhangrui/frontend-slides
- Used as: final pipeline stage — converts `CurationOutput` into self-contained HTML
- Input: structured content + destination vibe metadata
- Output: single HTML file with inline CSS/JS, no external dependencies
- Invoke via: `/frontend-slides` skill in Claude Code

### uv
- uv docs: https://docs.astral.sh/uv/
- Projects guide: https://docs.astral.sh/uv/guides/projects/
- Environments: https://docs.astral.sh/uv/pip/environments/
- CLI reference: https://docs.astral.sh/uv/reference/cli/

---

## Supporting docs

### Model Context Protocol
- Intro: https://modelcontextprotocol.io/docs/getting-started/intro
- Architecture: https://modelcontextprotocol.io/docs/learn/architecture
- Specification: https://modelcontextprotocol.io/specification/

---

## What the coding agent should look up

### Phase 1 — Adding MCP servers
- How to add a second and third `MCPServerStdio` instance in PydanticAI
- How to configure an npx-based MCP server vs Docker-based
- How to define Pydantic output schemas for typed agent responses
- tenacity retry patterns with async functions

### Phase 2 — Multi-agent pipeline
- PydanticAI agent-as-tool pattern (agent delegation)
- How to pass `ctx.deps` and `ctx.usage` between parent and sub-agents
- How to run multiple sub-agents in parallel
- How to configure different models per agent in PydanticAI
- Structured output from agents (`output_type` parameter)
- FunctionToolset patterns for direct Python tools alongside MCP toolsets

### Phase 3 — Output generation
- frontend-slides skill input format
- How to save output HTML to disk from Python
- How to pass image URLs into slide content

### When debugging behavior
- PydanticAI tool docs
- Dependency injection docs
- Airbnb MCP issues if results are inconsistent
- Google Maps MCP GitHub issues
- `fast-flights` docs and local Playwright behavior if flight search regresses

---

## Reading priority when blocked

1. `REQUIREMENTS.md`
2. `PRD.md`
3. PydanticAI multi-agent docs
4. PydanticAI toolsets docs
5. PydanticAI agent docs
6. PydanticAI output/structured output docs
7. Relevant tool repo (Airbnb, Brave, Google Maps, OpenWeather, fast-flights)
8. tenacity docs
9. uv docs
10. MCP spec

---

## Practical notes

- Terminal only, no web UI, no database.
- Do not optimize for production.
- All facts must come from tool calls — never hallucinate content.
- Partial failures: use tenacity retries, then graceful degradation (omit the section rather than guess).
- Log agent trace (tool calls, decisions, timing) to stdout so pipeline behavior is observable.
- HTML output saved to `output/` directory at project root.
- Prefer official docs over third-party examples.
