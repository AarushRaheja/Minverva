-- src/database/vst3_plugin.sql
CREATE TABLE vst3_plugin (
  id BIGSERIAL PRIMARY KEY,
  owner_id BIGINT NOT NULL REFERENCES users (id),
  title TEXT NOT NULL,
  amount_cents INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX vst3_plugin_owner_idx ON vst3_plugin (owner_id);
