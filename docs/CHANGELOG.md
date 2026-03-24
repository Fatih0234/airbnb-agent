# Changelog

## What this project does

**Airbnb Stay-Matching Copilot** is a terminal-based AI travel planning assistant. Given a destination, dates, trip type, and preferences, it runs a parallel multi-agent research pipeline and produces a fully styled, self-contained HTML travel brief.

A complete run outputs:
- **5 curated Airbnb stays** matched to dates, guests, and budget
- **Neighborhood profile** — safety, vibe, walkability
- **Weather forecast** with packing tips
- **6–10 activities** matched to the user's stated preferences
- **6–8 restaurant picks** with cuisine, price range, and descriptions
- **Commute options** (transit) to any target destinations (business/event trips)
- **Flight options** (if origin airport provided) via Google Flights MCP
- A **single-page HTML travel book** with sidebar navigation, images, and responsive layout

---

## Done — Session 2025-03-24

### Provider migration: OpenRouter → Google → MiniMax M2.7

**1. Switched from OpenRouter to Google Gemini**
- Changed `pydantic-ai-slim[openrouter]` → `[google]` extra
- Replaced `OpenRouterModel/OpenRouterProvider` with `GoogleModel/GoogleProvider` across all 8 agent files
- Updated config: `get_openrouter_api_key()` → `get_google_api_key()`, model name defaults updated
- Root cause: OpenRouter's `tool_choice` translation layer caused issues with certain models

**2. Diagnosed and fixed Gemini Flash Lite agent looping**
- `stays` agent was calling `airbnb_listing_details` for every listing, inflating context until the model lost track and looped — hitting pydantic-ai's 50-request limit after ~500s
- Fix: removed `airbnb_listing_details` calls entirely — `airbnb_search` results are sufficient, and images are scraped separately by `enrich_stays_with_images()`
- `activities` and `food` agents were calling `maps_place_details` per result, same loop problem
- Fix: removed Google Maps from both toolsets; `brave_local_search` alone is sufficient for discovery
- Added `usage_limits=UsageLimits(request_limit=8)` as a hard cap on activities/food to fail fast
- Fixed `pipeline.py` retry logic: `UsageLimitExceeded` no longer triggers tenacity retries (retrying a looping agent just loops again)
- Added curation retry with `wait_exponential` for transient 503s

**3. Switched from Google to MiniMax M2.7 (via Anthropic-compatible API)**
- `gemini-3.1-flash-lite-preview` was persistently 503ing for curation/slides (high demand)
- MiniMax M2.7 used via `https://api.minimax.io/anthropic` with pydantic-ai's Anthropic integration
- Wire-up: `anthropic.AsyncAnthropic(base_url=MINIMAX_BASE_URL, api_key=...)` passed to `AnthropicProvider(anthropic_client=...)`
- Changed `pydantic-ai-slim[google]` → `[anthropic]` extra
- M2.7's strong structured output and tool-calling eliminated the remaining looping issues
- All 9 agent files updated (stays, neighborhood, weather, activities, food, commute, flights, curation, slides)
- `MINIMAX_BASE_URL` constant added to `config.py`

**4. Fixed slides HTML truncation**
- HTML output was cut off at ~13KB (only first stay card partially rendered)
- Root cause: pydantic-ai Anthropic integration defaults to 1024 output tokens
- Fix: `model_settings=ModelSettings(max_tokens=16000)` added to slides `agent.run()` call
- Full HTML now generates at ~29KB with all sections rendered

**5. Flights agent integrated (by user)**
- New `app/agents/flights.py`: uses Brave (IATA lookup) + Google Flights MCP
- `app/schemas.py`: added `FlightOption`, `FlightsOutput`, `origin_airport` to `IntakeOutput`, `flights` to `CurationOutput`
- `app/intake.py`: added skippable "Where are you flying from?" prompt
- `app/mcp_client.py`: added `create_google_flights_mcp_server()`
- Pipeline: flights agent runs in parallel when origin airport is provided; omitted otherwise
- Slides: conditional Flights section (table with airline/times/price)

---

## Model dispatch (current)

| Model | Provider | Role | Agents |
|---|---|---|---|
| `MiniMax-M2.7` | MiniMax Anthropic API | Research | stays, neighborhood, weather, activities, food, commute, flights |
| `MiniMax-M2.7` | MiniMax Anthropic API | Synthesis + HTML | curation, slides |

Env vars: `MINIMAX_API_KEY`, `MODEL_NAME`, `FAST_MODEL_NAME`, `GOOGLE_MAPS_API_KEY`, `BRAVE_API_KEY`

---

## Stack

- **Runtime:** Python 3.13, uv
- **Agent framework:** pydantic-ai-slim (MCP + Anthropic extras)
- **LLM:** MiniMax M2.7 via Anthropic-compatible API
- **MCP servers:** Airbnb (Docker), Brave Search (Docker), OpenWeather (Docker), Google Maps (npx), Google Flights (Docker)
- **Retry:** tenacity (exponential backoff, no retry on UsageLimitExceeded)
- **Output:** JSON + self-contained HTML to `output/`
