# Service Map

## Public Services

| Service | Public URL | Owner |
| --- | --- | --- |
| KaosGDD launcher | `https://family.kaosgdd.net` | KaosGDD v2 placeholder |
| Paperless | `https://paperless.kaosgdd.net` | Paperless-ngx |
| Wiki.js | `https://wiki.kaosgdd.net` | Wiki.js |
| Files | `https://files.kaosgdd.net` | SFTPGo |
| Calendar | `https://calendar.kaosgdd.net` | Radicale |
| PDF | `https://pdf.kaosgdd.net` | Stirling-PDF |
| Vaultwarden | `https://vault.kaosgdd.net` | Vaultwarden |
| Supplies | inside `https://kaosgdd.net` | KaosGDD Brain + Radicale |
| ntfy | `https://ntfy.kaosgdd.net` | legacy `kaos` host for now |

## Internal Adapter URLs

| Service | Internal URL |
| --- | --- |
| KaosGDD portal | `http://100.94.208.16:8090` |
| KaosGDD calendar adapter | `http://100.94.208.16:8091` |
| KaosGDD Brain (shadow) | `http://100.94.208.16:8092` |
| Paperless | `http://100.94.208.16:8000` |
| Wiki.js | `http://100.94.208.16:3001` |
| SFTPGo HTTP | `http://100.94.208.16:8081` |
| SFTPGo SFTP | `100.94.208.16:2022` |
| Stirling-PDF | `http://100.94.208.16:8082` |
| Vaultwarden | `http://100.94.208.16:8083` |
| Radicale | `http://100.94.208.16:5232` |
| KaosSupplies legacy | `http://100.94.208.16:8008` |

## Adapter Env

Production adapter settings live outside this repo:

```text
/srv/kaos/secrets/kaosgdd-adapters.env
```

Do not commit production tokens.
