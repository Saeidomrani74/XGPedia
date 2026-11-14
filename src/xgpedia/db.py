"""ذخیره‌سازی MVP — SQLite + لایهٔ repository (مهاجرت‌پذیر به PostgreSQL).

گروه‌های جدول (بخش ۷ سند):
  دادهٔ فوتبال: competitions, seasons, teams, players, fixtures, match_events,
    lineups, fixture_statistics, player_statistics, injuries, availability_reports
  ردیابی منبع: data_sources, ingestion_runs, raw_payloads
  محتوا و انتشار: articles, posts, media_assets, publishing_logs
  جامعه و ربات: bot_users, subscriptions, prediction_entries, leaderboards,
    moderation_logs, admin_actions

فیلدهای مشترک حیاتی: provider_id, source_id, collected_at, event_time,
updated_at, season_id, status, confidence, raw_payload_hash
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.xgpedia.config import DATABASE_PATH

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS fixtures (
  fixture_id TEXT PRIMARY KEY,            -- "provider:12345"
  provider TEXT NOT NULL,
  competition TEXT NOT NULL,
  season TEXT NOT NULL,
  kickoff_utc TEXT NOT NULL,
  home_team TEXT NOT NULL,
  away_team TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'scheduled',
  raw_payload_hash TEXT,
  collected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fixture_statistics (
  fixture_id TEXT NOT NULL,
  team TEXT NOT NULL,
  metric TEXT NOT NULL,                  -- total_shots, expected_goals, ...
  value REAL,                            -- NULL = داده در دسترس نیست (هرگز 0 جایگزین نشود)
  n INTEGER,
  provider TEXT NOT NULL,
  collected_at TEXT NOT NULL,
  PRIMARY KEY (fixture_id, team, metric, provider)
);

CREATE TABLE IF NOT EXISTS raw_payloads (
  payload_hash TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  collected_at TEXT NOT NULL,
  file_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
  post_id INTEGER PRIMARY KEY AUTOINCREMENT,
  fixture_id TEXT NOT NULL,
  post_type TEXT NOT NULL,               -- preview | post_match | number_of_day | ...
  target_platform TEXT NOT NULL,         -- telegram | instagram | website | tiktok
  content_version INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'draft',  -- draft|validated|awaiting_approval|approved|scheduled|published|failed|corrected
  title TEXT, caption TEXT,
  fact_json TEXT,                        -- JSON واقعیت‌ها — منبع único تک‌نسخه
  created_at TEXT NOT NULL,
  UNIQUE (fixture_id, post_type, target_platform, content_version)  -- idempotency key
);

CREATE TABLE IF NOT EXISTS publishing_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id INTEGER NOT NULL REFERENCES posts(post_id),
  platform_message_id TEXT,
  permalink TEXT,
  published_at TEXT NOT NULL,
  result TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS moderation_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id INTEGER,
  admin_user_id INTEGER NOT NULL,
  action TEXT NOT NULL,                  -- approve | reject | edit | rebuild | mute | ban
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
CREATE INDEX IF NOT EXISTS idx_fixtures_kickoff ON fixtures(kickoff_utc);
"""


@contextmanager
def db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(SCHEMA)


if __name__ == "__main__":
    init_db()
    print(f"OK — database initialized at {DATABASE_PATH}")
