# REQUIREMENTS — Current Runtime Contract

This file describes what the repo is expected to do now. It replaces the older phased build checklist as the source of truth for maintainers.

## Functional Requirements

The app must:

1. accept trip intake from terminal prompts or `--input <scenario.json>`
2. validate the payload into `IntakeOutput`
3. run research for:
   - stays
   - neighborhood
   - activities
   - food
   - weather
   - flights when `origin_airport` is provided
4. save a structured JSON brief
5. generate a self-contained HTML travel book through the deterministic presentation system (`DeckSpec` builder, style preset selection, HTML renderer)
6. open the HTML output in the browser when generation succeeds

## Output Contract

### Core sections

- hero: destination, dates, thesis, key metrics
- recommendation: best overall stay and tradeoff note
- comparison: ranked stay shortlist
- stays: up to 5 Airbnb options
- neighborhood: safety, vibe, walkability, notable notes
- activities: curated list matched to `time_preferences`
- food: curated list matched to trip type and preferences
- weather: summary, temperature range, conditions, packing tips
- flights: optional, omitted on failure or when not requested

### Link and image expectations

- stay candidates expose a stable `id` that survives ranking and rendering
- stay cards keep the Airbnb listing URL and deterministic stay-image scraping
- activity and food items expose `source_url`
- activity and food images are best-effort, populated via deterministic metadata scraping from `source_url`
- HTML must surface actionable outbound links for activity and food cards when `source_url` exists

## Reliability Requirements

- partial agent failure must not abort the whole run if curation can still proceed
- failed agents must produce fallback empty outputs rather than guessed content
- failed agent runs must write debug logs to `output/debug/`
- retry behavior must avoid retrying obvious usage-limit failures
- search-backed agent execution must remain serialized enough to reduce rate-limit churn

## Regression Scenarios

The repo should keep working against saved scenario fixtures in `docs/scenarios/`, including:

- Lisbon
- Barcelona
- Istanbul
- Denver
- Sydney

Scenario runs should be suitable for:

- single end-to-end validation
- isolated agent debugging
- concurrent stress testing

## Known Constraints

- terminal only
- no database
- local execution only
- facts must come from tools or deterministic post-processing
- some third-party source pages will block scraping with `403` or return `404`; this should reduce image coverage only, not fail the run
- concurrent runs may cause flight search or search-backed stages to hit request limits
