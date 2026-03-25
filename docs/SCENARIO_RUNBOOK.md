# Scenario Runbook

This repo includes reusable JSON fixtures for repeatable end-to-end validation.

## Available Scenarios

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

All current fixtures are designed to exercise the full pipeline:

- flights enabled via `origin_airport`
- specific `time_preferences` for non-generic activities and food output

## Recommended Single-Run Regression

Use Lisbon or Barcelona for a representative full run:

```bash
uv run python main.py --input docs/scenarios/lisbon_workcation_roundtrip.json
uv run python main.py --input docs/scenarios/barcelona_business_roundtrip.json
```

## Parallel Stress Run

The Istanbul, Denver, and Sydney fixtures are useful together because they vary geography, flight lookup style, and research sources.

Recent concurrent run observations:

- Denver: full success
- Sydney: full success
- Istanbul: partial success; flights degraded under concurrent load due to request-limit exhaustion

Use those three when validating:

- concurrent scenario execution
- flight-search resilience
- graceful degradation
- activity/food `source_url` and image enrichment behavior across varied source sites

The newer Kyoto, Marrakech, Mexico City, Cape Town, and Buenos Aires fixtures are useful when validating:

- broader `trip_type` coverage beyond business/workcation
- more specific `time_preferences` steering for food and activity curation
- couple, event, family, and culture-led stay ranking behavior
- output tone changes across romantic, family, and nightlife-heavy briefs

## Expected App Behavior

For each scenario run:

1. load the JSON intake file
2. run stays, neighborhood, activities, food, weather, and optional flights
3. normalize and enrich activities/food with `source_url` and best-effort metadata images
4. run curation
5. save JSON to `output/`
6. save HTML to `output/`
7. attempt to open the HTML file in the browser

## Success Signals

In terminal output, look for:

- `Loaded trip intake from ...`
- `Researching your trip... this may take a minute.`
- `Generating HTML travel book...`
- either full success or a partial-results warning
- final JSON and HTML output paths

In JSON/HTML output, look for:

- 3-5 stay options
- stay map section in HTML when stay coordinates are present
- neighborhood summary
- weather guidance
- curated activities and food
- flight options when search succeeds
- `source_url` on activities and food
- HTML outbound links for activity and food cards

## Partial Runs

The pipeline is expected to degrade gracefully.

If one or more agents fail after retries:

- the failing agent name should be reported
- a debug artifact should be written to `output/debug/`
- JSON should still be saved if curation succeeds
- HTML may still be generated from the reduced dataset

## Debug A Single Agent

Rerun one agent against a saved scenario:

```bash
uv run python scripts/debug_agent.py --agent neighborhood --input docs/scenarios/lisbon_workcation_roundtrip.json
uv run python scripts/debug_agent.py --agent flights --input docs/scenarios/istanbul_workcation_roundtrip.json
```
