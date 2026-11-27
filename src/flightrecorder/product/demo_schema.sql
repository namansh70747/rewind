CREATE TABLE IF NOT EXISTS rewind_demo_job (
    id uuid PRIMARY KEY,
    owner text NOT NULL REFERENCES rewind_account(subject),
    action text NOT NULL CHECK (action IN ('capture', 'verify')),
    source_id text NOT NULL,
    source_digest text NOT NULL,
    recording_id uuid REFERENCES rewind_recording(id),
    replays integer NOT NULL DEFAULT 0,
    status text NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    cancel_requested boolean NOT NULL DEFAULT false,
    result jsonb,
    error text,
    created timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS rewind_demo_one_job
ON rewind_demo_job ((1)) WHERE status IN ('queued', 'running');
CREATE INDEX IF NOT EXISTS rewind_demo_owner_jobs ON rewind_demo_job (owner, created DESC);
