# ADR 0002: Keep Legacy Fax Bridge Temporarily

## Status

Superseded.

## Context

HylaFAX originally depended on the legacy KaosGDD backend for fax visibility
and notifications.

The legacy KaosGDD frontend can be stopped, but fax visibility must remain alive.

## Decision

The temporary bridge was retained until HylaFAX transport and Brain Telegram
notification/archive workers replaced it.

## Consequences

- HylaFAX owns transport.
- Brain owns Telegram notifications, the human fax archive, and fax automation.
- The old backend is no longer a notification dependency.

## Exit Criteria

The legacy backend can be stopped only after:

- incoming fax notifications work without it
- outgoing fax failure notifications work without it
- a replacement fax UI/API is available or explicitly deferred
