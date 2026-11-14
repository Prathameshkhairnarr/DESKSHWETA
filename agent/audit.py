"""
Audit log — SQLite-backed record of every tool call, task, and result.

Shweta can read recent activity with: "kya kiya abhi"
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / "logs" / "audit.db"
_DB_PATH.parent.mkdir(exist_ok=True)


class AuditLog:
    """Thread-safe SQLite audit log."""

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    goal TEXT,
                    state TEXT,
                    created_at REAL,
                    completed_at REAL,
                    final_reply TEXT,
                    steps_taken INTEGER DEFAULT 0,
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS tool_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    step_index INTEGER,
                    tool_name TEXT,
                    params TEXT,
                    result_status TEXT,
                    result_message TEXT,
                    duration_ms INTEGER,
                    ts REAL,
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
                );

                CREATE TABLE IF NOT EXISTS voice_commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT,
                    intent TEXT,
                    ts REAL
                );

                CREATE INDEX IF NOT EXISTS idx_tool_ts ON tool_calls(ts);
                CREATE INDEX IF NOT EXISTS idx_task_ts ON tasks(created_at);
            """)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Task lifecycle ────────────────────────────────────────────────────

    def log_task_start(self, task_id: str, goal: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO tasks(task_id, goal, state, created_at) VALUES(?,?,?,?)",
                (task_id, goal, "running", time.time()),
            )

    def log_task_done(
        self, task_id: str, state: str, final_reply: str = "",
        steps_taken: int = 0, error: str = ""
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE tasks SET state=?, completed_at=?, final_reply=?, steps_taken=?, error=? WHERE task_id=?",
                (state, time.time(), final_reply, steps_taken, error, task_id),
            )

    # ── Tool calls ────────────────────────────────────────────────────────

    def log_tool_call(
        self,
        task_id: str,
        step_index: int,
        tool_name: str,
        params: Dict[str, Any],
        result_status: str,
        result_message: str,
        duration_ms: int,
    ) -> None:
        try:
            with self._conn() as conn:
                conn.execute(
                    """INSERT INTO tool_calls
                       (task_id, step_index, tool_name, params, result_status, result_message, duration_ms, ts)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        task_id, step_index, tool_name,
                        json.dumps(params, ensure_ascii=False, default=str),
                        result_status, result_message[:500], duration_ms, time.time(),
                    ),
                )
        except Exception as exc:
            logger.debug("Audit log_tool_call failed: %s", exc)

    # ── Voice commands ────────────────────────────────────────────────────

    def log_voice_command(self, text: str, intent: str = "") -> None:
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO voice_commands(text, intent, ts) VALUES(?,?,?)",
                    (text, intent, time.time()),
                )
        except Exception:
            pass

    # ── Queries ───────────────────────────────────────────────────────────

    def recent_summary(self, n: int = 5) -> str:
        """Return a short Hinglish summary of the last N tasks (for 'kya kiya abhi')."""
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT goal, state, final_reply FROM tasks ORDER BY created_at DESC LIMIT ?",
                    (n,),
                ).fetchall()

            if not rows:
                return "Abhi tak koi task nahi kiya."

            lines = []
            for row in rows:
                state_icon = {"done": "✅", "failed": "❌", "running": "⏳",
                              "cancelled": "🚫"}.get(row["state"], "•")
                reply_snippet = (row["final_reply"] or "")[:60]
                lines.append(f"{state_icon} {row['goal'][:50]}"
                              + (f" — {reply_snippet}" if reply_snippet else ""))
            return "Yeh kiya main ne:\n" + "\n".join(lines)
        except Exception as exc:
            return f"Audit log read nahi hua: {exc}"

    def tool_call_history(self, task_id: str) -> List[Dict]:
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM tool_calls WHERE task_id=? ORDER BY step_index",
                    (task_id,),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def stats(self) -> Dict[str, Any]:
        try:
            with self._conn() as conn:
                total_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
                done_tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE state='done'").fetchone()[0]
                total_calls = conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0]
            return {
                "total_tasks": total_tasks,
                "done_tasks": done_tasks,
                "total_tool_calls": total_calls,
            }
        except Exception:
            return {}


# Module-level singleton
audit_log = AuditLog()
