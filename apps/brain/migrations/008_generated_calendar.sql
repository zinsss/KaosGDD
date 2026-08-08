CREATE TABLE generated_calendar_settings (
    id smallint PRIMARY KEY CHECK (id = 1),
    market_days_enabled boolean NOT NULL DEFAULT true,
    claim_day_enabled boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO generated_calendar_settings (id)
VALUES (1)
ON CONFLICT (id) DO NOTHING;

COMMENT ON TABLE generated_calendar_settings IS
    'Display controls for Brain-generated Market Day and Claim Day VEVENTs. Event content remains authoritative in Radicale.';
