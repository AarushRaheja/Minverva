-- src/database/users.sql
CREATE TABLE users (
  id BIGSERIAL PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  session_token TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
