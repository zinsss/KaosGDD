# Mobile v1 Design Direction

KaosGDD v2 starts mobile-first.

The old KaosGDD is a design reference, not an implementation base. The useful parts are the compact operator rhythm: quick date scanning, dense task rows, service shortcuts, and small contextual signals.

## First Mobile Surface

The first mobile screen should feel like a daily clinic cockpit:

- top status strip
- service shortcuts
- calendar month with selected-day agenda
- task queue
- bottom navigation

The first production-backed implementation should keep the UI independent from backend ownership. Calendar and task data should flow through adapter contracts, with Radicale becoming the authoritative calendar backend when ready.

## Reuse Guidance

Reuse as design direction:

- compact task list hierarchy
- due/status color language
- event count markers
- selected-day agenda pattern
- weather as quiet context

Do not reuse directly:

- old database-backed task/event services
- old deprecated module navigation
- old reminder/journal/scribble coupling
- family calendar as the first task/calendar base

ROUN and caregiver wage should be separate modules after the first task/calendar surface has a clean shape.
