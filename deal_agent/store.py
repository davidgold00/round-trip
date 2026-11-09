"""SQLite state and review queue. No publication methods live in this module."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .trace import digest, stamp


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY, started TEXT NOT NULL, finished TEXT, status TEXT, stats TEXT);
        CREATE TABLE IF NOT EXISTS documents (
          id TEXT PRIMARY KEY, meta TEXT NOT NULL, text_path TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'ready');
        CREATE TABLE IF NOT EXISTS jobs (
          url TEXT PRIMARY KEY, kind TEXT NOT NULL, meta TEXT NOT NULL,
          done INTEGER NOT NULL DEFAULT 0, document_id TEXT REFERENCES documents(id));
        CREATE TABLE IF NOT EXISTS cursors (source TEXT PRIMARY KEY, since TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS chunks (
          document_id TEXT REFERENCES documents(id), chunk_no INTEGER, result TEXT NOT NULL,
          PRIMARY KEY(document_id, chunk_no));
        CREATE TABLE IF NOT EXISTS issues (
          id INTEGER PRIMARY KEY, run_id TEXT, document_id TEXT, stage TEXT,
          error TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS candidates (
          id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL,
          document_id TEXT REFERENCES documents(id), deal TEXT NOT NULL,
          verification TEXT NOT NULL, reconcile TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending', created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit (
          id INTEGER PRIMARY KEY, candidate_id TEXT REFERENCES candidates(id), actor TEXT NOT NULL,
          action TEXT NOT NULL, created TEXT NOT NULL, payload TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'applied');
        CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
          BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS audit_payload_immutable BEFORE UPDATE OF
          candidate_id, actor, action, created, payload ON audit
          BEGIN SELECT RAISE(ABORT, 'audit payload is immutable'); END;
        """)

    def close(self):
        self.db.close()

    def rows(self, query: str, args=()) -> list[dict]:
        return [dict(row) for row in self.db.execute(query, args)]

    def start(self, run_id):
        self.db.execute(
            "INSERT INTO runs VALUES(?,?,NULL,'running',NULL)", (run_id, stamp())
        )

    def finish(self, run_id, stats, status="complete"):
        self.db.execute(
            "UPDATE runs SET finished=?,status=?,stats=? WHERE id=?",
            (stamp(), status, encode(stats), run_id),
        )

    def issue(self, run_id, document_id, stage, error):
        self.db.execute(
            "INSERT INTO issues VALUES(NULL,?,?,?,?,?)",
            (run_id, document_id, stage, str(error), stamp()),
        )

    def job(self, url: str, kind: str, meta: dict):
        self.db.execute(
            "INSERT OR IGNORE INTO jobs(url,kind,meta) VALUES(?,?,?)",
            (url, kind, encode(meta)),
        )

    def save_document(
        self, meta: dict, raw: bytes, text: str, directory: Path
    ) -> tuple[str, bool]:
        # Text content dedupes syndicated/reissued documents; retain every source
        # URL, raw hash and metadata on the jobs table, not just the first source.
        ident = digest(text)
        directory.mkdir(parents=True, exist_ok=True)
        raw_hash = digest(raw)
        raw_path, text_path = directory / f"{raw_hash}.raw", directory / f"{ident}.txt"
        if not raw_path.exists():
            raw_path.write_bytes(raw)
        if not text_path.exists():
            text_path.write_text(text, encoding="utf-8")
        meta = {
            **meta,
            "raw_sha256": raw_hash,
            "text_sha256": ident,
            "raw_path": str(raw_path),
            "fetched_at": stamp(),
        }
        new = (
            self.db.execute(
                "INSERT OR IGNORE INTO documents(id,meta,text_path) VALUES(?,?,?)",
                (ident, encode(meta), str(text_path)),
            ).rowcount
            == 1
        )
        self.db.execute(
            "UPDATE jobs SET done=1,document_id=?,meta=? WHERE url=?",
            (ident, encode(meta), meta["source_url"]),
        )
        return ident, new

    def chunk(self, ident: str, index: int) -> dict | None:
        row = self.db.execute(
            "SELECT result FROM chunks WHERE document_id=? AND chunk_no=?",
            (ident, index),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def save_chunk(self, ident, index, result):
        self.db.execute(
            "INSERT OR REPLACE INTO chunks VALUES(?,?,?)",
            (ident, index, encode(result)),
        )

    def propose(
        self, document_id: str, deal: dict, verification: dict, reconcile: dict
    ) -> bool:
        identity = {
            k: deal[k]
            for k in (
                "source_entity",
                "target_entity",
                "deal_type",
                "announced_date",
                "amount_usd",
                "term_or_duration",
            )
        }
        identity["document"] = document_id
        key = digest(encode(identity))
        return (
            self.db.execute(
                """INSERT OR IGNORE INTO candidates
            (id,fingerprint,document_id,deal,verification,reconcile,created)
            VALUES(?,?,?,?,?,?,?)""",
                (
                    "a_" + key[:20],
                    key,
                    document_id,
                    encode(deal),
                    encode(verification),
                    encode(reconcile),
                    stamp(),
                ),
            ).rowcount
            == 1
        )

    def candidates(self, status="pending") -> list[dict]:
        rows = self.rows(
            "SELECT * FROM candidates WHERE status=? ORDER BY created,id", (status,)
        )
        for row in rows:
            for key in ("deal", "verification", "reconcile"):
                row[key] = json.loads(row[key])
        return rows
