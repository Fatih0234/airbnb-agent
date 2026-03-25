# Tavily Workflow

This repo uses Tavily in two different ways:

1. Runtime MCP integration inside the Python travel pipeline
2. Optional Tavily Agent Skills for maintainers and coding agents

The Python app only depends on the Tavily MCP server. Tavily Agent Skills are not loaded by the app and are not required to run the pipeline.

## Runtime MCP

The runtime search provider is Tavily MCP, launched locally with:

```bash
npx -y tavily-mcp@latest
```

The app passes:

- `TAVILY_API_KEY`
- `DEFAULT_PARAMETERS={"search_depth":"advanced","max_results":5,"include_images":false,"include_raw_content":false}`

Current runtime usage:

- `neighborhood` uses `tavily-search` only
- `activities` uses `tavily-search` first and should rely on snippets; `tavily-extract` is a rare fallback on at most one URL
- `food` uses `tavily-search` first and should rely on snippets; `tavily-extract` is a rare fallback on at most one URL
- `flights` prefers local `search_airports` first and uses `tavily-search` only as a fallback for unresolved airport-code lookup before direct `fast-flights` search

## Optional Tavily Agent Skills

These are optional maintainer workflows for Codex/Claude Code style agents.

- `/tavily-best-practices`
  - Use when revising Tavily-backed prompt patterns or search/extract strategies.
- `/tavily-search`
  - Use for quick source checks while debugging a failing destination or validating agent claims.
- `/tavily-research`
  - Use for cited background research when creating new scenario files or validating destination coverage.
- `/tavily-map`
  - Use to find the right documentation page before extracting it.
- `/tavily-crawl`
  - Use for external documentation research or offline maintainer reference workflows.

These skills are for developer productivity only. They are not part of the runtime travel pipeline.
