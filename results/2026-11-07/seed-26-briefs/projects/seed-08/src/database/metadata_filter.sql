-- src/database/metadata_filter.sql
CREATE TABLE metadata_filter (
  id BIGSERIAL PRIMARY KEY,
  owner_id BIGINT NOT NULL REFERENCES users (id),
  title TEXT NOT NULL,
  amount_cents INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX metadata_filter_owner_idx ON metadata_filter (owner_id);
