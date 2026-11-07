-- src/database/audio_track.sql
CREATE TABLE audio_track (
  id BIGSERIAL PRIMARY KEY,
  owner_id BIGINT NOT NULL REFERENCES users (id),
  title TEXT NOT NULL,
  amount_cents INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX audio_track_owner_idx ON audio_track (owner_id);
