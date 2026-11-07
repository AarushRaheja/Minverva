-- src/database/thermal_profile.sql
CREATE TABLE thermal_profile (
  id BIGSERIAL PRIMARY KEY,
  owner_id BIGINT NOT NULL REFERENCES users (id),
  title TEXT NOT NULL,
  amount_cents INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX thermal_profile_owner_idx ON thermal_profile (owner_id);
