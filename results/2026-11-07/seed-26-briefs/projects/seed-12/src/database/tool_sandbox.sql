-- src/database/tool_sandbox.sql
CREATE TABLE tool_sandbox (
  id BIGSERIAL PRIMARY KEY,
  owner_id BIGINT NOT NULL REFERENCES users (id),
  title TEXT NOT NULL,
  amount_cents INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX tool_sandbox_owner_idx ON tool_sandbox (owner_id);
