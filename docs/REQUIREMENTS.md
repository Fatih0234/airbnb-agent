# REQUIREMENTS — Build Phases

## Phase 0 — Completed ✓
Single conversational agent connected to Airbnb MCP. Terminal loop, message history, basic stay search and listing details. Proved the model/tool loop works.

---

## Phase 1 — Foundation & MCP Expansion

Goal: Extend the tool stack and add retry infrastructure before touching the agent logic.

Steps:
1. Add `openweather` MCP server to `mcp_client.py`
2. Add `mcp-google-map` (npx-based) MCP server to `mcp_client.py`
3. Add `tenacity` to dependencies for retry logic on tool calls and agent runs
4. Define Pydantic output schemas for each sub-agent (typed structured data)
5. Verify all four MCP servers start and expose their tools correctly

Schemas to define:
- `IntakeOutput` — all user inputs structured (destination, dates, trip type, budget, guests, target destinations, time preferences)
- `StaysOutput` — list of up to 5 stay candidates with images, price, link, key amenities
- `NeighborhoodOutput` — safety summary, vibe, walkability notes
- `ActivitiesOutput` — curated activity list with images, descriptions
- `FoodOutput` — restaurant/cafe list with images, cuisine type, price range
- `WeatherOutput` — forecast for travel dates, packing recommendation
- `CommuteOutput` — transit options and times to user's target destinations, map URL
- `CurationOutput` — final assembled content ready for slide generation (all sections + image URLs)

---

## Phase 2 — Agent Pipeline

Goal: Rebuild from single chat agent to orchestrated multi-agent pipeline.

Steps:
1. Build Intake Agent — terminal prompts collecting all `IntakeOutput` fields
2. Build research sub-agents (each uses assigned model + MCP tools, returns typed schema):
   - Stays Agent → Airbnb MCP → `StaysOutput`
   - Neighborhood Agent → Brave (llm_context + web search) → `NeighborhoodOutput`
   - Activities Agent → Brave (local + web) + Maps (explore_area) → `ActivitiesOutput`
   - Food Agent → Brave (local) + Maps (search_nearby) → `FoodOutput`
   - Weather Agent → OpenWeather MCP → `WeatherOutput`
   - Commute Agent → Maps (directions transit, distance_matrix) → `CommuteOutput`
3. Build Orchestrator — wires all sub-agents as tools via agent-as-tool pattern, dispatches in parallel where possible
4. Build Curation Agent — takes all sub-agent outputs, produces `CurationOutput` with all sections and image URLs
5. Add tenacity retry wrappers on each agent run
6. Add trace logging (tool calls, agent decisions, timing)

Model assignment:
- Research agents: `stepfun/step-3.5-flash:free`
- Curation + Orchestrator: `minimax/minimax-m2.7`

---

## Phase 3 — Output Generation

Goal: Turn curation output into the HTML travel book.

Steps:
1. Wire `/frontend-slides` skill as the final pipeline stage
2. Feed `CurationOutput` into the skill with destination vibe metadata
3. Save HTML output to disk (e.g. `output/{destination}_{dates}.html`)
4. Open in browser automatically after generation (optional convenience)
5. Test full pipeline end-to-end with a real trip query

---

## Phase 4 — Quality & Iteration (future)

Not yet scoped. Potential directions:
- Richer slide styling per trip type / destination vibe
- User confirmation step before slide generation
- Multiple output formats (PDF export from HTML)
- Web UI intake form (replaces terminal)
- Caching research results for repeat queries to same destination
- Adding more trip types
- Support for multi-city / multi-leg trips

---

## Constraints (all phases)

- Terminal only, no web UI
- No database
- Local execution, no deployment
- All facts must come from tool calls — no hallucination
- Partial tool failures handled with retries, graceful degradation if retries exhausted
