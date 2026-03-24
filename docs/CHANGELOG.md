# Changelog

## Done — Session 2026-03-24 (Source links, enrichment, scenarios)

- Added `source_url` to activities and food outputs so recommendations are directly linkable in JSON and HTML
- Added deterministic activity/food image enrichment from source-page metadata (`og:image`, `twitter:image`, JSON-LD, `image_src`)
- Updated HTML cards to show source hostname and outbound `Visit link` CTA for activities and food
- Added reusable Istanbul, Denver, and Sydney full-pipeline scenario fixtures
- Validated concurrent end-to-end runs across Istanbul, Denver, and Sydney
- Observed one concurrent-flight degradation case in Istanbul and one recoverable Google Maps commute error in Sydney

## Done — Session 2026-03-24 (Tavily migration)

- Replaced Brave MCP with Tavily MCP for runtime web research in `neighborhood`, `activities`, `food`, and flight airport-code lookup
- Switched env/config from `BRAVE_API_KEY` to `TAVILY_API_KEY`
- Added provider-neutral serialized search retries instead of Brave-specific retry logic
- Kept Tavily Agent Skills as an optional maintainer workflow only; they are documented but not used by the Python runtime
- Preserved deterministic curation and deterministic HTML rendering

## What this project does

**Airbnb Stay-Matching Copilot** is a terminal-based AI travel planning assistant. Given a destination, dates, trip type, and preferences, it runs a parallel multi-agent research pipeline and produces a fully styled, self-contained HTML travel brief.

A complete run outputs:
- **5 curated Airbnb stays** matched to dates, guests, and budget
- **Neighborhood profile** — safety, vibe, walkability
- **Weather forecast** with packing tips
- **6–10 activities** matched to the user's stated preferences
- **6–8 restaurant picks** with cuisine, price range, and descriptions
- **Commute options** (transit) to any target destinations (business/event trips)
- **Flight options** (if origin airport provided) via direct `fast-flights` search with local Playwright
- A **single-page HTML travel book** with sidebar navigation, images, and responsive layout

---

## Done — Session 2026-03-24

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
- New `app/agents/flights.py`: uses Brave (IATA lookup) + Google Flights
- `app/schemas.py`: added `FlightOption`, `FlightsOutput`, `origin_airport` to `IntakeOutput`, `flights` to `CurationOutput`
- `app/intake.py`: added skippable "Where are you flying from?" prompt
- Pipeline: flights agent runs in parallel when origin airport is provided; omitted otherwise
- Slides: conditional Flights section (table with airline/times/price)

**6. Replaced Google Flights MCP with direct `fast-flights[local]` integration**
- Root cause: the Docker `mcp/google-flights` image was receiving `consent.google.com` pages and parsing them as "no flights found"
- Added `fast-flights[local]` dependency and installed Playwright-backed local Chromium support
- New `app/flight_search.py`: exact-date and flexible date-window search helpers plus normalization and de-duplication
- `app/agents/flights.py`: switched from Docker MCP to direct Python tools via `FunctionToolset`
- `app/mcp_client.py`: removed the unused Google Flights Docker factory
- Result: live IST → Tokyo searches now return real structured options under MiniMax M2.7

---

## Model dispatch (current)

| Model | Provider | Role | Agents |
|---|---|---|---|
| `MiniMax-M2.7` | MiniMax Anthropic API | Research | stays, neighborhood, weather, activities, food, commute, flights |
| `MiniMax-M2.7` | MiniMax Anthropic API | Synthesis + HTML | curation, slides |

Env vars: `MINIMAX_API_KEY`, `MODEL_NAME`, `FAST_MODEL_NAME`, `GOOGLE_MAPS_API_KEY`, `TAVILY_API_KEY`

---

## Stack

- **Runtime:** Python 3.13, uv
- **Agent framework:** pydantic-ai-slim (MCP + Anthropic extras)
- **LLM:** MiniMax M2.7 via Anthropic-compatible API
- **MCP servers:** Airbnb (Docker), Tavily (npx), OpenWeather (Docker), Google Maps (npx)
- **Direct flight search:** `fast-flights[local]` + Playwright
- **Retry:** tenacity (exponential backoff, no retry on UsageLimitExceeded)
- **Output:** JSON + self-contained HTML to `output/`
