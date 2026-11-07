-- src/database/deepspeed_zero_three.sql
CREATE TABLE deepspeed_zero_three (
  id BIGSERIAL PRIMARY KEY,
  owner_id BIGINT NOT NULL REFERENCES users (id),
  title TEXT NOT NULL,
  amount_cents INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX deepspeed_zero_three_owner_idx ON deepspeed_zero_three (owner_id);
