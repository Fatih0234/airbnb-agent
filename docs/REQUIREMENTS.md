# REQUIREMENTS.md

## Objective
Build the smallest useful local prototype of the Airbnb Stay-Matching Copilot using:
- Python
- uv
- PydanticAI
- OpenRouter
- Airbnb MCP server

The goal is not production quality.
The goal is to prove the core agent loop works.

## Required stack
Use:
- Python
- uv for project and virtual environment management
- PydanticAI as the agent framework
- OpenRouter as the model router/provider layer
- Airbnb MCP server as the external tool source

## Build philosophy
- keep scope small
- keep code runnable
- avoid unnecessary abstractions
- prefer direct, readable code
- terminal only
- no premature architecture

## Functional requirements

### FR1. Terminal app
- The prototype must run locally from the terminal.
- The user must be able to type messages and receive agent responses.
- Session state can be in-memory only.

### FR2. Model setup
- The app must connect to one configurable model via OpenRouter.
- The model name should be configurable.
- Missing credentials should fail clearly.

### FR3. Agent framework
- The app must use PydanticAI as the main agent framework.
- The agent should have a clear system prompt.
- The agent should support tool use and structured dependencies as needed.

### FR4. MCP connection
- The app must connect to the Airbnb MCP server.
- The app must expose or access:
  - `airbnb_search`
  - `airbnb_listing_details`
- The app should fail clearly if MCP is unavailable.

### FR5. Agent behavior
- The agent should ask clarifying questions before searching if key constraints are missing.
- The agent should call tools when listing-specific or search-specific data is needed.
- The agent should not invent listing details.
- The agent should summarize results in a readable way.

### FR6. Logging and debugging
- The prototype should log enough information to debug:
  - model setup issues
  - MCP connection issues
  - tool call failures
  - empty or unclear tool results
- stdout logging is enough.

### FR7. Error handling
- If a tool call fails, the app should explain that clearly.
- If search results are empty, the agent should ask the user to refine constraints.
- If listing details are unavailable, the agent should say so instead of guessing.

## Non-requirements
Do not build or spend time on:
- frontend UI
- voice pipelines
- authentication
- databases
- vector databases
- RAG pipelines
- background jobs
- cloud deployment
- Docker orchestration beyond what is needed to run the MCP
- production monitoring
- analytics
- payments
- booking flows
- long-term memory
- multi-agent systems

## Minimal project structure
A simple structure is enough, for example:

```text
/project-root
  README.md
  PRD.md
  REQUIREMENTS.md
  DOCS.md
  STARTER_PROMPT.md
  .env.example
  pyproject.toml
  main.py
  app/
    agent.py
    config.py
    mcp_client.py
    prompt.py
```

## Configuration requirements
At minimum, support:
- OpenRouter API key
- model name
- optional base URL if needed
- Airbnb MCP server command / configuration
- optional debug flag

## Prompt requirements
The runtime prompt should instruct the agent to:
- act as a stay-matching copilot
- ask for missing essential constraints before searching
- use tools for listing-specific facts
- avoid hallucinating
- summarize results and tradeoffs clearly
- provide direct links when available

## Acceptance checklist
The prototype is acceptable when all are true:
- [ ] local app launches
- [ ] virtual environment setup is documented
- [ ] model connection works
- [ ] MCP connection works
- [ ] `airbnb_search` can be called
- [ ] `airbnb_listing_details` can be called
- [ ] the agent can ask follow-up questions
- [ ] the agent can summarize results clearly
- [ ] failure cases are readable
- [ ] the code remains simple and local-first

## Nice-to-have only if trivial
Only add these if very easy:
- colored terminal logs
- transcript save to a local file
- a single demo script
- a mock mode for testing without live MCP

## Final instruction
Do not overbuild.

Implement the shortest path to a working prototype that demonstrates:

**chat -> reasoning -> MCP tool call -> result -> useful answer**
