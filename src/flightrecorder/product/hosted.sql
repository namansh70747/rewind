CREATE TABLE IF NOT EXISTS rewind_schema (version integer PRIMARY KEY);
CREATE TABLE IF NOT EXISTS rewind_account (subject text PRIMARY KEY, email text NOT NULL);
CREATE TABLE IF NOT EXISTS rewind_oauth (
    state text PRIMARY KEY, browser_hash text NOT NULL, verifier text NOT NULL,
    nonce text NOT NULL, action text NOT NULL, expires timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS rewind_session (
    token_hash text PRIMARY KEY, subject text NOT NULL REFERENCES rewind_account(subject),
    csrf text NOT NULL, expires timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS rewind_recording (
    id uuid PRIMARY KEY, owner text REFERENCES rewind_account(subject),
    demo boolean NOT NULL DEFAULT false, bundle jsonb NOT NULL,
    summary jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((owner IS NULL) = demo)
);
CREATE INDEX IF NOT EXISTS rewind_recording_owner ON rewind_recording (owner, created_at DESC, id DESC);
INSERT INTO rewind_schema VALUES (1) ON CONFLICT DO NOTHING;
