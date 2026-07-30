CREATE TABLE brain_settings (
    scope text NOT NULL,
    setting_key text NOT NULL,
    value jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, setting_key)
);

COMMENT ON TABLE brain_settings IS
    'KaosGDD-owned orchestration settings only; never user calendar, task, document, PACS, or service-owned data.';
