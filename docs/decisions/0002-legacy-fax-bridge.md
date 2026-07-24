# ADR 0002: Keep Legacy Fax Bridge Temporarily

## Status

Accepted.

## Context

HylaFAX currently runs on the legacy `kaos` host. Incoming fax handling calls the legacy KaosGDD backend, which records fax state and sends Pushover notifications.

The legacy KaosGDD frontend can be stopped, but fax visibility must remain alive.

## Decision

Keep the legacy KaosGDD backend running as the fax bridge until KaosFaxMail or another dedicated fax service replaces it.

## Consequences

- KaosGDD v2 does not need to solve fax immediately.
- The old backend remains a dependency for fax/Pushover.
- The old frontend can stay stopped while v2 work proceeds.

## Exit Criteria

The legacy backend can be stopped only after:

- incoming fax notifications work without it
- outgoing fax failure notifications work without it
- a replacement fax UI/API is available or explicitly deferred
