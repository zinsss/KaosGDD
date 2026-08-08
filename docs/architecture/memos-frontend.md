# Custom Memos Frontend

## Verified Baseline

Production runs `neosmemo/memos:stable`, reporting Memos `0.29.1`, with data at
`/srv/kaos/data/memos`. Memos owns its SQLite database and uploaded attachments.
KaosGDD does not read or write that database.

The API contract was checked against the live service and the official
`usememos/memos` `v0.29.1` protobuf and generated OpenAPI files.

Definitely available:

- password and SSO sign-in, refresh, current user, and sign-out
- memo create, list, get, update with field masks, and delete
- Markdown `content`
- `PRIVATE`, `PROTECTED`, and `PUBLIC` visibility
- pinning
- tags extracted by Memos from content
- CEL list filters including `content.contains(...)`, `tag in [...]`, creator,
  visibility, pin, task-list, link, code, and creation date
- pagination and ordering by pin/create/update/name
- attachment create/list/update/delete and memo attachment assignment
- relations, comments, reactions, and share links

API limitations and deliberate first-slice exclusions:

- Tags are output-only. The frontend changes tags by editing standard `#tag`
  Markdown in memo content.
- Search is substring/CEL filtering, not a ranked full-text search API.
- Attachments are supported but deferred until upload, assignment, cleanup, and
  file-serving paths are tested together.
- Memos has no receipt-printer abstraction. Printing belongs to KaosPrint.
- Tiptap Markdown conversion is not part of Memos and must be tested locally.

## Deployment

One `kaosgdd-memos-web` image runs twice:

```text
memos.kaosgdd.net/app/          -> personal frontend -> Memos API
kaosgdd.net/memos-app/          -> embedded personal frontend -> Memos API
family.kaosgdd.net/memos-app/   -> family frontend   -> Memos API
```

The upstream Memos UI remains at `memos.kaosgdd.net/` during the preview phase.
After the custom client is stable, the personal frontend may take `/` while an
explicit upstream path remains available for uncommon Memos features.

Both hosts proxy `/api/v1/*` to the same Memos service. Memos sets
`memos_refresh` with `Path=/`, `HttpOnly`, `SameSite=Lax`, `Secure` on HTTPS, and
no `Domain`. Browser cookie scoping therefore isolates personal and Family
sessions. The custom frontend holds the 15-minute access token in memory only.
No password, personal access token, or refresh token is stored in JavaScript.

The embedded personal frontend uses the main host's `/memos-app/` and
`/api/v1/*` routes so Cloudflare Access is not nested inside an iframe. Its
host-only Memos session is separate from a direct `memos.kaosgdd.net` session.

Cloudflare Access remains the outer user gate. Memos authentication remains the
inner account boundary and selects the canonical personal or Family account.

## WYSIWYG and Markdown

Phase 2 adds Tiptap to `apps/memos-web`; it does not add another frontend.
Markdown remains the canonical wire and storage representation.

The risky boundary is Markdown round-tripping. A WYSIWYG editor cannot preserve
every arbitrary Markdown construct byte-for-byte. The supported editing subset
will be H1-H4, emphasis, strike, links, bullet/ordered/task lists, blockquotes,
inline/code blocks, and horizontal rules. Fixtures must cover existing Memos
Markdown, nested lists, task states, escaped characters, soft breaks, and mode
switching. Unsupported constructs should remain available in Markdown mode and
must not be silently discarded on a WYSIWYG save.

Family defaults to WYSIWYG. Personal may remember its editor preference in
host-local storage. This preference is frontend-only state, not memo data.

## KaosPrint

KaosPrint should run on the always-on home device that has USB or LAN access to
the 80 mm printer. It is separate from Memos, Brain, and either frontend account.

```text
personal or Family frontend
  -> authenticated same-origin relay
  -> Tailscale/private KaosPrint API
  -> normalized receipt renderer
  -> ESC/POS driver interface
  -> USB or LAN printer
```

The public browser must not reach KaosPrint or raw ESC/POS directly. A later
Brain relay can validate the Cloudflare Access identity, load or receive the
authorized memo payload, assign an idempotency key, and submit over Tailscale.
KaosPrint stores only job metadata and transient render data needed for retry.

Driver and renderer interfaces must stay separate so USB ESC/POS can be replaced
by LAN ESC/POS. Duplicate suppression should key on source, memo ID, content
digest, and a short time window. `POST /print/memo` and `GET /health` are the
initial API; unrestricted raw printing should not be exposed publicly.

## Delivery Order

1. Phase 1 REST client, isolated auth, feed, CRUD, Markdown rendering, search,
   tags, pin, and visibility.
2. Tiptap dual-mode editor with Markdown fixture tests.
3. Attachment lifecycle.
4. KaosPrint service, relay, receipt fixtures, duplicate protection, and QR.
5. Additional Memos features only when a daily workflow requires them.
