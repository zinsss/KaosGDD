CREATE TABLE event_presets (
    id text PRIMARY KEY,
    owner text NOT NULL CHECK (owner IN ('zin', 'wife', 'family')),
    name text NOT NULL CHECK (length(btrim(name)) > 0),
    title text NOT NULL CHECK (length(btrim(title)) > 0),
    all_day boolean NOT NULL DEFAULT true,
    start_time time without time zone NOT NULL DEFAULT '09:00',
    end_time time without time zone NOT NULL DEFAULT '10:00',
    alarm_time time without time zone,
    memo text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_event_presets_owner
ON event_presets(owner, updated_at DESC);

COMMENT ON TABLE event_presets IS
    'Cross-device event templates for the ZiN, Bling02, and shared Family portal scopes.';
