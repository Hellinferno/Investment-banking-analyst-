"""Persistent request pacing and conservative local budgets for free providers."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
import time


class RequestBudget:
    def __init__(self, provider: str, key: str, path: Path, daily_limit: int, requests_per_minute: int):
        self.provider = provider
        self.path = path
        self.key_id = hashlib.sha256(key.encode()).hexdigest()[:16]
        self.daily_limit = daily_limit
        self.interval = 60 / requests_per_minute

    def reserve(self, remote_used: int = 0) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        day = datetime.now(timezone.utc).date().isoformat()
        now = time.time()
        with sqlite3.connect(self.path, timeout=5) as db:
            db.execute("CREATE TABLE IF NOT EXISTS usage (key_id TEXT, day TEXT, calls INTEGER, last_call REAL, blocked_until REAL, PRIMARY KEY(key_id, day))")
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT calls, last_call, blocked_until FROM usage WHERE key_id=? AND day=?", (self.key_id, day)).fetchone()
            calls, last_call, blocked_until = row or (0, 0.0, 0.0)
            if blocked_until > now:
                raise RuntimeError(f"{self.provider} is cooling down after a rate limit; retry in {int(blocked_until - now) + 1} seconds.")
            calls = max(calls, int(remote_used or 0))
            if calls >= self.daily_limit:
                raise RuntimeError(f"{self.provider} local daily request budget ({self.daily_limit}) is exhausted; wait for the UTC-day reset.")
            start = max(now, last_call + self.interval)
            if start - now > 30:
                raise RuntimeError(f"{self.provider} request queue is full; retry later.")
            db.execute("INSERT OR REPLACE INTO usage VALUES (?, ?, ?, ?, ?)", (self.key_id, day, calls + 1, start, blocked_until))
        if start > now:
            time.sleep(start - now)

    def cooldown(self, seconds: int) -> None:
        day = datetime.now(timezone.utc).date().isoformat()
        with sqlite3.connect(self.path, timeout=5) as db:
            db.execute("UPDATE usage SET blocked_until=? WHERE key_id=? AND day=?", (time.time() + seconds, self.key_id, day))
