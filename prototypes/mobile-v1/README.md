# KaosGDD Mobile v1 Prototype

This is the first mobile-first design prototype for KaosGDD v2.

It is intentionally static:

- no production service calls
- no database access
- no Radicale writes
- no PACS/Fax/Supplies side effects

## Run

Open `index.html` directly in a browser, or serve this directory with any static file server.

```sh
python3 -m http.server 8099 --directory prototypes/mobile-v1
```

## Design Intent

The prototype uses old KaosGDD as a design reference only.

Kept:

- dense clinic-operator layout
- compact task rows
- month calendar with selected-day agenda
- service launcher
- weather/status as context

Not kept:

- old backend assumptions
- deprecated reminder/journal/scribble surfaces
- old monolithic navigation
- direct database ownership
