# STARTER_PROMPT.md

You are building the **v1 prototype** of an **Airbnb Stay-Matching Copilot**.

Build only the minimum required to prove the core product idea.

## What this project is
This is a local, terminal-first, single-agent prototype.

The prototype should show that one Python agent can:
- connect to a model through OpenRouter
- connect to the Airbnb MCP server
- call the Airbnb tools
- respond usefully in a terminal conversation

## Stack
Use:
- Python
- uv
- PydanticAI
- OpenRouter
- Airbnb MCP server

## Required docs to read first
Before writing code, read:
1. `PRD.md`
2. `REQUIREMENTS.md`
3. `DOCS.md`

Use the official docs listed in `DOCS.md` whenever implementation details are unclear.

## First setup requirements
- initialize the project with uv
- create a virtual environment with uv
- install dependencies with uv
- create a minimal runnable project
- create `.env.example`
- create a small `README.md` with setup and run instructions

## Product behavior
The agent is a stay-matching copilot.
It should:
- ask for missing essential trip constraints
- use `airbnb_search` when it has enough context
- use `airbnb_listing_details` when listing-specific detail is needed
- avoid hallucinating facts
- summarize options and tradeoffs clearly
- provide direct links if the tool returns them

## Available Airbnb tools
Assume the relevant external tools are:
- `airbnb_search`
- `airbnb_listing_details`

## Constraints
Keep the scope narrow.

Do not add:
- web UI
- frontend framework
- voice
- database
- auth
- booking flow
- long-term memory
- multi-agent orchestration
- cloud deployment
- analytics
- unnecessary abstractions

## Preferred implementation style
- simple files
- direct code
- incremental progress
- keep the app runnable after each major step
- good enough logs for debugging
- clear failure messages

## Minimal deliverable
Produce a runnable local prototype with:
- source code
- uv project setup
- virtual environment setup
- PydanticAI agent
- OpenRouter configuration
- Airbnb MCP connection
- terminal chat loop
- `.env.example`
- README

## Runtime expectations
A tester should be able to:
1. start the app locally
2. type a natural request such as:
   - "Find me a place in Amsterdam for 2 guests next weekend"
   - "Show me more details about the first result"
3. observe the agent using tools
4. receive a useful answer in the terminal

## Success condition
The project is successful when the core loop works:

**user input -> agent reasoning -> MCP tool call -> result -> useful response**

## Final instruction
Do not overbuild.

Optimize for the fastest clean path to a working prototype that proves the concept.
