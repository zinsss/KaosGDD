CREATE TABLE mail_organizer_settings (
    id smallint PRIMARY KEY CHECK (id = 1),
    runs_per_day smallint NOT NULL DEFAULT 1 CHECK (runs_per_day IN (1, 2)),
    first_time time NOT NULL DEFAULT '09:00',
    second_time time NOT NULL DEFAULT '17:00',
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (runs_per_day = 1 OR first_time < second_time)
);

INSERT INTO mail_organizer_settings (id)
VALUES (1)
ON CONFLICT (id) DO NOTHING;

COMMENT ON TABLE mail_organizer_settings IS
    'Schedule for the Telegram Naver INBOX organizer. Naver IMAP remains authoritative for mail.';
