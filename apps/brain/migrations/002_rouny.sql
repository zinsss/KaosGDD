CREATE TABLE rouny_documents (
    scope text PRIMARY KEY,
    revision bigint NOT NULL DEFAULT 0 CHECK (revision >= 0),
    templates jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(templates) = 'array')
);

COMMENT ON TABLE rouny_documents IS
    'KaosGDD-owned Rouny timetable templates, stored as one revisioned document per portal scope.';
