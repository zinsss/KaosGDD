CREATE TABLE family_ledger_entries (
    id text PRIMARY KEY,
    sort_order bigint NOT NULL UNIQUE,
    entry_date date NOT NULL,
    category text NOT NULL CHECK (length(btrim(category)) > 0),
    amount bigint CHECK (amount IS NULL OR amount >= 0),
    details text NOT NULL DEFAULT '',
    account_delta bigint NOT NULL DEFAULT 0,
    cash_delta bigint NOT NULL DEFAULT 0,
    gift_delta bigint NOT NULL DEFAULT 0,
    source_row integer,
    source_checksum text NOT NULL DEFAULT '',
    locked boolean NOT NULL DEFAULT false,
    revision integer NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_by text NOT NULL DEFAULT 'family',
    updated_by text NOT NULL DEFAULT 'family',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE INDEX idx_family_ledger_active_order
ON family_ledger_entries(sort_order)
WHERE deleted_at IS NULL;

CREATE TABLE family_ledger_audit (
    id bigserial PRIMARY KEY,
    entry_id text NOT NULL,
    action text NOT NULL CHECK (action IN ('import', 'create', 'update', 'delete')),
    actor text NOT NULL,
    before_data jsonb,
    after_data jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_family_ledger_audit_created
ON family_ledger_audit(created_at DESC, id DESC);

COMMENT ON TABLE family_ledger_entries IS
    'Family medical association ledger. PostgreSQL is authoritative; XLSX files are exports and recovery snapshots.';

COMMENT ON TABLE family_ledger_audit IS
    'Append-only audit trail for imported, created, edited, and deleted family ledger entries.';
