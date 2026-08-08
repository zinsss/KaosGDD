# Family Ledger

The Family portal owns the Maya Hospital medical association ledger. It replaces
the working Google Sheet without making Google Sheets part of the production
dependency chain.

## Authority

- Brain PostgreSQL is the source of truth.
- The Family portal is the only browser profile allowed to use the API.
- XLSX files are portable exports and recovery snapshots, not a second database.
- Every create, update, delete, and imported row is recorded in an append-only
  audit table.
- Updates require the last known row revision. A stale browser receives `409`
  instead of overwriting a newer edit.

The ledger preserves the spreadsheet columns:

```text
날짜 | 사용 구분 | 금액 | 상세 내용 | 계좌 | 현금 | 상품권
```

Only the first four columns are entered. Brain derives the three balance columns
from the category and amount. The imported `인수인계` opening row is locked.

## API

```text
GET    /api/ledger
POST   /api/ledger/entries
PUT    /api/ledger/entries/{id}
DELETE /api/ledger/entries/{id}
GET    /api/ledger/export.xlsx
POST   /api/ledger/backups
```

Cloudflare Access's authenticated email header is stored as the audit actor when
available. Requests are still restricted by the Family portal host at Brain.

## Backups

Brain writes a validated XLSX after every successful mutation and at 03:20 daily.
Daily files are kept for 90 days; month-end files are retained indefinitely.
Each workbook has a SHA-256 sidecar and these sheets:

- `거래내역`
- `월별요약`
- `변경기록`
- `정보`

A separate 03:35 timer creates a PostgreSQL custom-format dump. The XLSX makes
the data human-readable without KaosGDD; the PostgreSQL dump preserves the full
audit and revision model.
