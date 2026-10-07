-- Trendwatcher MVP: sources, events, summaries
-- Соответствует docs/db-schema.md

CREATE TABLE sources (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  label text NOT NULL,
  url text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('rss', 'api', 'sitemap')),
  enabled boolean NOT NULL DEFAULT true,
  last_fetched_at timestamptz,
  last_success_at timestamptz,
  consecutive_errors integer NOT NULL DEFAULT 0 CHECK (consecutive_errors >= 0)
);

CREATE TABLE events (
  url text PRIMARY KEY,
  source_id bigint NOT NULL REFERENCES sources (id),
  title text,
  published_at timestamptz,
  collected_at timestamptz NOT NULL DEFAULT now(),
  metrics jsonb
);

CREATE TABLE summaries (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  period_start timestamptz NOT NULL,
  period_end timestamptz NOT NULL,
  body text NOT NULL,
  sent_at timestamptz
);
