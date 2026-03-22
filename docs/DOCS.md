# DOCS.md

This file lists the main documentation the coding agent should use while building the prototype.

## Read these first
1. `PRD.md`
2. `REQUIREMENTS.md`
3. this `DOCS.md`

## Main stack docs

### PydanticAI
Use these as the main implementation docs:
- Overview: https://ai.pydantic.dev/
- Agent docs: https://ai.pydantic.dev/agents/
- Dependencies: https://ai.pydantic.dev/dependencies/
- Tools: https://ai.pydantic.dev/tools/
- Built-in tools: https://ai.pydantic.dev/builtin-tools/
- MCP overview: https://ai.pydantic.dev/mcp/overview/
- OpenRouter model docs: https://ai.pydantic.dev/models/openrouter/
- Output and streaming docs: https://ai.pydantic.dev/output/
- Messages and history: https://ai.pydantic.dev/message-history/

### OpenRouter
Use for model access and configuration:
- Quickstart: https://openrouter.ai/docs/quickstart
- API overview: https://openrouter.ai/docs/api-reference/overview
- Parameters: https://openrouter.ai/docs/api-reference/parameters
- Models: https://openrouter.ai/models

### Airbnb MCP
Use as the external tool server:
- Docker Hub overview: https://hub.docker.com/mcp/server/openbnb-airbnb/overview
- Docker Hub tools: https://hub.docker.com/mcp/server/openbnb-airbnb/tools
- GitHub repo: https://github.com/openbnb-org/mcp-server-airbnb
- GitHub issues: https://github.com/openbnb-org/mcp-server-airbnb/issues

### uv
Use for project setup and virtual environments:
- uv docs: https://docs.astral.sh/uv/
- Projects guide: https://docs.astral.sh/uv/guides/projects/
- Environments: https://docs.astral.sh/uv/pip/environments/
- Installing Python: https://docs.astral.sh/uv/guides/install-python/
- CLI reference: https://docs.astral.sh/uv/reference/cli/

## Supporting docs

### Model Context Protocol
Use if MCP behavior is unclear:
- Intro: https://modelcontextprotocol.io/docs/getting-started/intro
- Architecture: https://modelcontextprotocol.io/docs/learn/architecture
- Specification: https://modelcontextprotocol.io/specification/

## What the coding agent should look up

### When setting up the project
Look up:
- how to initialize a Python project with uv
- how to create a virtual environment with uv
- how to install packages with uv
- how to run a Python app with uv

### When wiring the model
Look up:
- PydanticAI OpenRouter model configuration
- required environment variables
- minimal agent setup
- message history / conversation handling if needed

### When wiring tools / MCP
Look up:
- PydanticAI MCP overview
- how PydanticAI integrates with MCP servers
- how to connect to the Airbnb MCP server
- how to restrict tool use to the required Airbnb tools if needed

### When debugging behavior
Look up:
- PydanticAI tool docs
- dependency injection docs
- built-in tools docs only if they simplify the prototype
- Airbnb MCP issues if results seem inconsistent

## Reading priority when blocked
If uncertain, check docs in this order:
1. `REQUIREMENTS.md`
2. `PRD.md`
3. PydanticAI MCP overview
4. PydanticAI agent docs
5. PydanticAI OpenRouter docs
6. PydanticAI tools docs
7. Airbnb MCP repo / Docker Hub
8. uv docs
9. MCP spec

## Practical notes for v1
- Keep everything local and terminal-based.
- Do not add a web UI.
- Do not add a database.
- Do not optimize for production.
- The purpose is to verify the model/tool loop.
- Use the simplest possible project layout.
- Prefer official docs over third-party examples.

## The core outcome to prove
The coding agent should build a prototype that can:
1. start locally,
2. connect to OpenRouter,
3. connect to the Airbnb MCP server,
4. call `airbnb_search`,
5. call `airbnb_listing_details`,
6. answer in a useful, cautious way.
