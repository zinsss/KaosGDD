ALTER TABLE document_queue
ADD COLUMN source_key text;

ALTER TABLE document_queue
DROP CONSTRAINT document_queue_source_check;

ALTER TABLE document_queue
ADD CONSTRAINT document_queue_source_check
CHECK (source IN ('hwp', 'stirling', 'shortcut', 'telegram', 'upload'));

ALTER TABLE document_queue
ADD CONSTRAINT document_queue_source_key_unique UNIQUE (source_key);

COMMENT ON COLUMN document_queue.source_key IS
    'Optional idempotency key supplied by an external intake source.';
