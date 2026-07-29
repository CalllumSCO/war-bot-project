-- Durable War Bot tables (v1). Safe to re-run (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS players (
  discord_id BIGINT PRIMARY KEY,
  friend_code TEXT,
  lounge_name TEXT,
  lounge_player_id BIGINT,
  link_source TEXT,
  lounge_verified BOOLEAN NOT NULL DEFAULT FALSE,
  last_fc_verified_at TIMESTAMPTZ,
  mmr INT NOT NULL DEFAULT 10000,
  wins INT NOT NULL DEFAULT 0,
  losses INT NOT NULL DEFAULT 0,
  ratings JSONB NOT NULL DEFAULT '{}'::jsonb,
  record JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS teams (
  guild_id BIGINT PRIMARY KEY,
  data JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS guild_configs (
  guild_id BIGINT PRIMARY KEY,
  guild_name TEXT,
  data JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS war_results (
  id BIGSERIAL PRIMARY KEY,
  result_id TEXT UNIQUE,
  completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS war_results_completed_at_idx
  ON war_results (completed_at DESC);
