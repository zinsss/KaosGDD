# Private Telegram Bot API

## Purpose

The official Telegram Bot API server runs on `kaos` in local mode. It removes
the hosted Bot API's small bot file-transfer ceiling while keeping Brain as the
only owner of KaosGDD bot behavior.

This service is not a second bot and does not poll updates itself. It replaces
`https://api.telegram.org` as Brain's Bot API endpoint.

## Requirements

Create an application at `my.telegram.org` and record its numeric API ID and API
hash. These are Telegram application credentials, not the bot token.

Store them only on production:

```bash
sudo install -d -m 0700 /srv/kaos/secrets
sudo install -m 0600 /dev/null /srv/kaos/secrets/telegram-bot-api.env
sudoedit /srv/kaos/secrets/telegram-bot-api.env
```

Use:

```env
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
```

## Build On Kaos

The official server is a large TDLib C++ build. Build it on production `kaos`
only during a quiet maintenance window. Monitor temperature, memory, disk, and
load while it builds; PACS uptime takes priority and the build must be stopped
if it affects production.

```bash
cd /srv/projects/KaosGDD/ops/telegram-bot-api
docker build -t kaos-telegram-bot-api:adfd7f6 .
```

The Control Center is reserved for Wake-on-LAN transmission and is not the
image build host.

The image is pinned to upstream commit
`adfd7f6a8e990272851777eeb3ae0def4216f161`.

## Install On Production

```bash
sudo install -d -m 0750 /srv/kaos/stacks/platform/telegram-bot-api
sudo install -d -m 0750 -o 10001 -g 10001 /srv/kaos/data/telegram-bot-api
sudo cp ops/telegram-bot-api/compose.production.yaml \
  /srv/kaos/stacks/platform/telegram-bot-api/compose.yaml
cd /srv/kaos/stacks/platform/telegram-bot-api
sudo docker compose up -d
```

Port `8081` binds only to the production Tailscale address. Do not add this
service to Caddy, cloudflared, or a public Docker port.

## Bot Migration

Telegram allows one Bot API location for a bot token. Perform this as a planned
short outage for Telegram workflows:

1. Stop Brain so its single `getUpdates` consumer is idle.
2. Call the hosted Bot API `logOut` method once for the KaosGDD bot token.
3. Set Brain's `TELEGRAM_API_BASE_URL=http://100.94.208.16:8081`.
4. Set `TELEGRAM_LOCAL_FILE_ROOT=/var/lib/telegram-bot-api`.
5. Mount `/srv/kaos/data/telegram-bot-api` read-only at the same absolute path
   inside Brain.
6. Restart Brain.
7. Verify `getMe`, Brain status, one Fax-topic action, Memos-topic protection,
   and one Documents-topic PDF.

Do not run hosted `logOut` until the local service is built, reachable, and its
credentials are present. Do not run a second `getUpdates` consumer.

Brain Compose additions after migration:

```yaml
services:
  brain:
    environment:
      TELEGRAM_API_BASE_URL: http://100.94.208.16:8081
      TELEGRAM_LOCAL_FILE_ROOT: /var/lib/telegram-bot-api
    volumes:
      - /srv/kaos/data/telegram-bot-api:/var/lib/telegram-bot-api:ro
```

The Bot API data directory may contain downloaded Telegram files. Treat it as a
working cache rather than a document backup. Paperless remains the permanent
document archive and the normal retention policy still applies to Brain's
document queue.
