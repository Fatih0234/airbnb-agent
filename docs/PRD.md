# PRD — Trip Planning Copilot

## Product idea

A terminal-based agentic pipeline that takes a user's trip constraints and wishes, researches everything autonomously, and produces a self-contained HTML travel book the user can browse to make decisions. No chat loop — one input session, one rich output.

## The problem

Planning a trip involves juggling many tabs and sources: Airbnb for stays, Google Maps for commute times, TripAdvisor for activities, weather forecasts, neighborhood safety research, restaurant hunting. This takes hours and the results are scattered. Most people settle for "good enough" because doing it thoroughly is tedious.

## The solution

One pipeline that collects your constraints once, dispatches specialized agents to research in parallel, curates the best options, and assembles everything into a single travel book — stays, activities, food, weather, commute logistics, neighborhood brief — all sourced from real data, not hallucinated.

## User type

- Travelers (leisure and business) who value thoroughness over speed
- People planning trips to unfamiliar cities who want local context they can trust
- Business travelers who need to understand commute logistics before booking
- People who are comfortable with a terminal during testing/early access

## Trip types supported

| Type | Primary focus |
|---|---|
| Vacation | Activities, food, atmosphere, neighborhood vibe |
| Business | Commute to office/venue, transit options, practical logistics |
| Workcation | Wifi quality, coworking nearby, leisure mix |
| Weekend getaway | Short trip, convenience, proximity, high-density activities |
| Family trip | Space, kid-friendly filters, nearby parks/attractions |
| Romantic / honeymoon | Ambiance, couples activities, romantic dining |
| Event-based | Proximity to venue as primary constraint, dates locked |

## Output

A single self-contained HTML file saved to disk. Sections:
- Cover (destination, dates, trip type)
- Stay options (5 best matches with images, price, key details, link)
- Neighborhood brief (safety, vibe, character)
- Weather & packing (forecast for travel dates)
- Activities (curated to how the user wants to spend time)
- Food picks (restaurants, cafes, local cuisine)
- Commute & logistics (transit times to target destinations, map)

## What makes this different

- Fully sourced — every claim comes from a tool call, nothing invented
- Trip-type aware — research priorities shift based on why you're traveling
- User-directed activities — not generic "top 10" lists, shaped by what the user tells us
- Rich output — images, maps, links, all in one file

## Current status

Prototype phase. Terminal only, no web UI, no database. Purpose is to validate the agent pipeline and output quality before any productization.
