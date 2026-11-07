-- src/database/astronomer.sql
CREATE TABLE astronomer (
  id BIGSERIAL PRIMARY KEY,
  owner_id BIGINT NOT NULL REFERENCES users (id),
  title TEXT NOT NULL,
  amount_cents INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX astronomer_owner_idx ON astronomer (owner_id);
