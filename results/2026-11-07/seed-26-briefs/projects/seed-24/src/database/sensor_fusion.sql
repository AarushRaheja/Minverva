-- src/database/sensor_fusion.sql
CREATE TABLE sensor_fusion (
  id BIGSERIAL PRIMARY KEY,
  owner_id BIGINT NOT NULL REFERENCES users (id),
  title TEXT NOT NULL,
  amount_cents INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX sensor_fusion_owner_idx ON sensor_fusion (owner_id);
