CREATE TABLE recurring_task_definitions (
    id text PRIMARY KEY,
    owner text NOT NULL CHECK (owner IN ('zin', 'wife', 'family')),
    adapter_profile text NOT NULL CHECK (adapter_profile IN ('main', 'family')),
    collection_id text NOT NULL,
    title text NOT NULL CHECK (length(btrim(title)) > 0),
    memo text NOT NULL DEFAULT '',
    first_due_date date NOT NULL,
    due_time time without time zone NOT NULL DEFAULT '10:00',
    priority text NOT NULL DEFAULT '' CHECK (priority IN ('', '1', '5', '9')),
    frequency text NOT NULL CHECK (frequency IN ('daily', 'weekly', 'monthly', 'yearly')),
    enabled boolean NOT NULL DEFAULT true,
    active_uid text,
    active_collection_id text,
    active_due_date date,
    next_due_date date,
    last_completed_uid text,
    last_completed_at timestamptz,
    last_error text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_recurring_task_definitions_enabled
ON recurring_task_definitions(enabled, adapter_profile);

CREATE INDEX idx_recurring_task_definitions_owner
ON recurring_task_definitions(owner, updated_at DESC);

COMMENT ON TABLE recurring_task_definitions IS
    'KaosGDD Brain recurrence definitions and generated VTODO UID mappings. Actual task data remains authoritative in Radicale.';
