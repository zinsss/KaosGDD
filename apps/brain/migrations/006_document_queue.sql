CREATE TABLE document_queue (
    id text PRIMARY KEY,
    profile text NOT NULL CHECK (profile IN ('main', 'family')),
    source text NOT NULL CHECK (source IN ('hwp', 'stirling', 'shortcut', 'upload')),
    original_filename text NOT NULL CHECK (length(btrim(original_filename)) > 0),
    stored_filename text NOT NULL UNIQUE CHECK (length(btrim(stored_filename)) > 0),
    content_type text NOT NULL DEFAULT 'application/pdf',
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    sha256 text NOT NULL CHECK (length(sha256) = 64),
    status text NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'submitted')),
    paperless_filename text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    submitted_at timestamptz
);

CREATE INDEX idx_document_queue_profile_created
ON document_queue(profile, created_at DESC);

CREATE INDEX idx_document_queue_expiry
ON document_queue(expires_at);

COMMENT ON TABLE document_queue IS
    'Temporary PDFs awaiting user preview, Paperless submission, or expiry cleanup.';
