# JSON Intake Design

## Goal

Add a file-based intake mode so the full trip-planning pipeline can be run non-interactively for repeatable end-to-end tests.

## Scope

- Keep the current interactive terminal prompts as the default workflow.
- Add an optional CLI flag for a JSON intake file.
- Validate the file against `IntakeOutput` before running the pipeline.
- Commit one realistic scenario file that exercises flights and commute.

## Chosen approach

Use `uv run python main.py --input <file.json>`.

Why:

- Minimal change to the current architecture.
- No duplicate runner script.
- Easy to document and easy to reuse in regression runs.
- No new dependency required beyond the standard library `json` module.

## Data flow

1. Parse CLI arguments in `main.py`.
2. If `--input` is present, load and validate the JSON file into `IntakeOutput`.
3. If `--input` is absent, fall back to `collect_intake()`.
4. Run the existing pipeline unchanged from that point onward.

## Error handling

- Missing file: exit with a clear `SystemExit` message.
- Invalid JSON: exit with a clear `SystemExit` message.
- Schema validation failure: exit with a clear `SystemExit` message.

## Test scenario

Use a Lisbon workcation scenario with:

- `origin_airport` set, to exercise flights
- `trip_type=workcation`, to exercise commute
- realistic budget and time preferences, to exercise stays, food, and activities

## Follow-up

If this workflow proves useful, the next extension is batchable scenario testing from multiple JSON files. YAML is intentionally out of scope for this first pass.
