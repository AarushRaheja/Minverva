-- src/database/state_checkpoint.sql
CREATE TABLE state_checkpoint (
  id BIGSERIAL PRIMARY KEY,
  owner_id BIGINT NOT NULL REFERENCES users (id),
  title TEXT NOT NULL,
  amount_cents INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX state_checkpoint_owner_idx ON state_checkpoint (owner_id);
