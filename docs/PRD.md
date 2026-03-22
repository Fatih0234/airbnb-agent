# PRD.md

## Product
Airbnb Stay-Matching Copilot (V1)

## Goal
Build the smallest possible local prototype of a conversational Airbnb discovery assistant.

The prototype should prove that one Python agent can:
- connect to a model through OpenRouter
- connect to the Airbnb MCP server
- call Airbnb MCP tools successfully
- hold a simple terminal conversation
- use tool results to help a user refine a stay search

This is an experimentation build, not a production product.

## Product shape
This version is:
- single-agent
- terminal-first
- local
- iterative
- tool-centric

This version is not:
- a web app
- a voice app
- a booking engine
- a production deployment
- a multi-agent system

## Core user problem
A user wants help finding a suitable Airbnb stay, but normal filtering and browsing is tedious.
The agent should ask for the right constraints, search listings, inspect listings, and explain tradeoffs.

## Primary user
For V1, the user is the builder or teammate testing the app manually in the terminal.

## Main workflow
1. User runs the app locally.
2. User describes a trip or stay need.
3. Agent asks clarifying questions if critical constraints are missing.
4. Agent calls `airbnb_search`.
5. Agent presents a small shortlist.
6. User asks follow-up questions about one or more listings.
7. Agent calls `airbnb_listing_details` when needed.
8. Agent summarizes fit, tradeoffs, and next steps.

## Available external tools
The Airbnb MCP server exposes:
- `airbnb_search`
- `airbnb_listing_details`

These are the only required external tools for V1.

## User stories
1. As a tester, I can start the prototype in the terminal.
2. As a tester, I can describe a destination and preferences in plain language.
3. As a tester, the agent can ask follow-up questions before searching.
4. As a tester, the agent can call Airbnb search and show understandable results.
5. As a tester, the agent can inspect one listing in more detail.
6. As a tester, the agent can explain why a listing might or might not fit.
7. As a tester, I can see enough logging to know whether the model and tools are working.

## What the agent should collect before searching
Only collect what is needed to search usefully:
- destination
- dates or trip length
- number of guests
- budget preference
- must-have constraints
- optional preferences only when helpful

## Agent behavior
- Be concise and practical.
- Ask for missing critical constraints before searching.
- Use tools instead of guessing listing-specific details.
- Do not hallucinate pricing, amenities, or availability.
- Present a small number of relevant options.
- Summarize tradeoffs clearly.
- Give direct links when the tool returns them.
- Be transparent when information is incomplete or uncertain.

## Success criteria
V1 is successful if:
- the app runs locally from the terminal
- OpenRouter model access works
- Airbnb MCP connection works
- `airbnb_search` can be called successfully
- `airbnb_listing_details` can be called successfully
- the app can complete a basic search conversation
- the output is understandable to a human tester

## Non-goals
Do not build these in V1:
- frontend UI
- React / Next.js
- authentication
- persistent database
- long-term memory
- booking or payment flow
- user accounts
- analytics dashboards
- deployment automation
- advanced observability
- multi-agent coordination
- vector search / RAG
- production hardening

## Risks and limitations
- The Airbnb MCP is scraper-backed and may be brittle.
- Tool results may be incomplete, delayed, or inconsistent.
- The model may overuse tools unless prompted carefully.
- Terminal output can become noisy if not formatted clearly.

## Guiding implementation principle
Keep the implementation minimal and testable.

The core loop to prove is:

**user request -> agent reasoning -> MCP tool call -> result interpretation -> useful response**
