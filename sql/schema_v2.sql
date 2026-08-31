-- Cloud SQL v2: matchmaking + SR + profile cosmetics

ALTER TABLE players ADD COLUMN IF NOT EXISTS bio TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS mkc_player_id BIGINT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS mkc_url TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS lounge_url TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS x_url TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS bluesky_url TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS youtube_url TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS twitch_url TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS discord_avatar_url TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS discord_username TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS display_name TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS supporter BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE players ADD COLUMN IF NOT EXISTS accent_color TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS chat_name_color TEXT;

CREATE TABLE IF NOT EXISTS player_ratings (
  discord_id BIGINT NOT NULL,
  track TEXT NOT NULL,
  role TEXT NOT NULL,
  mu DOUBLE PRECISION NOT NULL DEFAULT 25.0,
  sigma DOUBLE PRECISION NOT NULL DEFAULT 8.333333333333334,
  placement_count INT NOT NULL DEFAULT 0,
  revealed BOOLEAN NOT NULL DEFAULT FALSE,
  season_games INT NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (discord_id, track, role)
);

CREATE TABLE IF NOT EXISTS queue_parties (
  party_id TEXT PRIMARY KEY,
  invite_code TEXT UNIQUE,
  captain_discord_id BIGINT,
  guild_id BIGINT,
  data JSONB NOT NULL,
  status TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS queue_parties_captain_idx ON queue_parties (captain_discord_id);
CREATE INDEX IF NOT EXISTS queue_parties_status_idx ON queue_parties (status);

CREATE TABLE IF NOT EXISTS hub_posts (
  war_id TEXT PRIMARY KEY,
  board TEXT NOT NULL,
  party_id TEXT,
  author_id BIGINT,
  search_mode TEXT,
  status TEXT,
  data JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS hub_posts_board_status_idx ON hub_posts (board, status, search_mode);
CREATE INDEX IF NOT EXISTS hub_posts_party_idx ON hub_posts (party_id);

CREATE TABLE IF NOT EXISTS ally_requests (
  request_id TEXT PRIMARY KEY,
  war_id TEXT,
  requester_discord_id BIGINT,
  status TEXT,
  data JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ally_requests_war_idx ON ally_requests (war_id, status);

CREATE TABLE IF NOT EXISTS match_requests (
  request_id TEXT PRIMARY KEY,
  target_war_id TEXT,
  requester_war_id TEXT,
  status TEXT,
  data JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS match_requests_target_idx ON match_requests (target_war_id, status);

CREATE TABLE IF NOT EXISTS party_invites (
  invite_id TEXT PRIMARY KEY,
  party_id TEXT NOT NULL,
  from_discord_id BIGINT NOT NULL,
  target_discord_id BIGINT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  data JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS party_invites_target_idx ON party_invites (target_discord_id, status);
CREATE INDEX IF NOT EXISTS party_invites_party_idx ON party_invites (party_id, status);

CREATE TABLE IF NOT EXISTS match_sessions (
  session_id TEXT PRIMARY KEY,
  data JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS match_messages (
  id BIGSERIAL PRIMARY KEY,
  session_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  author_discord_id BIGINT,
  author_name TEXT,
  body TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS match_messages_session_idx
  ON match_messages (session_id, channel, created_at);

CREATE TABLE IF NOT EXISTS mkc_tournament_allowlist (
  event_key TEXT PRIMARY KEY,
  display_name TEXT,
  weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
  verified BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS event_bus (
  id BIGSERIAL PRIMARY KEY,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS event_bus_created_idx ON event_bus (id);

CREATE TABLE IF NOT EXISTS lineup_ratings (
  lineup_id TEXT PRIMARY KEY,
  track TEXT NOT NULL,
  member_ids BIGINT[] NOT NULL,
  mu DOUBLE PRECISION NOT NULL DEFAULT 25.0,
  sigma DOUBLE PRECISION NOT NULL DEFAULT 8.333333333333334,
  games_together INT NOT NULL DEFAULT 0,
  revealed BOOLEAN NOT NULL DEFAULT FALSE,
  wins INT NOT NULL DEFAULT 0,
  losses INT NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS lineup_ratings_members_idx ON lineup_ratings USING GIN (member_ids);
CREATE INDEX IF NOT EXISTS lineup_ratings_track_idx ON lineup_ratings (track);

-- Patreon membership sync (webhook-driven supporter perks)
CREATE TABLE IF NOT EXISTS patreon_memberships (
  member_id TEXT PRIMARY KEY,
  patreon_user_id TEXT NOT NULL,
  discord_id BIGINT,
  patron_status TEXT NOT NULL,
  pledge_cents INT,
  campaign_id TEXT,
  last_event_type TEXT,
  last_event_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  data JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS patreon_memberships_discord_idx ON patreon_memberships (discord_id);
CREATE INDEX IF NOT EXISTS patreon_memberships_user_idx ON patreon_memberships (patreon_user_id);

ALTER TABLE patreon_memberships ADD COLUMN IF NOT EXISTS next_charge_date TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS patreon_webhook_events (
  event_key TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Supporter tiers + perk fields (v1.0)
ALTER TABLE players ADD COLUMN IF NOT EXISTS supporter_tier TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS display_name_custom BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE players ADD COLUMN IF NOT EXISTS favorite_track TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS profile_alias TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS lineup_name_color TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS supporter_expires_at TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS players_profile_alias_idx ON players (LOWER(profile_alias)) WHERE profile_alias IS NOT NULL;

-- Backfill legacy boolean supporter flag into tier.
UPDATE players SET supporter_tier = 'supporter' WHERE supporter = TRUE AND (supporter_tier IS NULL OR supporter_tier = '');
