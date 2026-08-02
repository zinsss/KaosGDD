CREATE TABLE supply_presets (
    normalized_name text PRIMARY KEY,
    name text NOT NULL,
    last_used_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_supply_presets_last_used_at
ON supply_presets(last_used_at DESC);

COMMENT ON TABLE supply_presets IS
    'KaosGDD supplies recent-name history. Actual buy-list items are VTODO records in Radicale.';
