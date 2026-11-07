"""
Task Manager — background task queue with SQLite persistence.

Tasks survive restarts; state machine: queued → running → done/failed/cancelled.
Voice control: "ruk ja" → pause, "wo task cancel kar" → cancel.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from agent.types import AgentTask, TaskState

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / "logs" / "tasks.db"
_DB_PATH.parent.mkdir(exist_ok=True)


class TaskManager:
    """Thread-safe task queue with SQLite persistence."""

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._tasks: Dict[str, AgentTask] = {}
        self._init_db()
        self._load_pending()

    # ── DB ────────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    goal TEXT,
                    state TEXT,
                    created_at REAL,
                    started_at REAL,
                    completed_at REAL,
                    final_reply TEXT,
                    steps_taken INTEGER DEFAULT 0,
                    error TEXT
                );
            """)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _save(self, task: AgentTask) -> None:
        try:
            with self._conn() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO tasks
                    (task_id, goal, state, created_at, started_at, completed_at,
                     final_reply, steps_taken, error)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (
                    task.task_id, task.goal, task.state.value,
                    task.created_at, task.started_at, task.completed_at,
                    task.final_reply, task.steps_taken, task.error,
                ))
        except Exception as exc:
            logger.debug("Task save failed: %s", exc)

    def _load_pending(self) -> None:
        """Mark any 'running' tasks from before restart as failed."""
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE state IN ('queued','running')"
                ).fetchall()
                for row in rows:
                    conn.execute(
                        "UPDATE tasks SET state='failed', error=? WHERE task_id=?",
                        ("Interrupted by restart", row["task_id"]),
                    )
            logger.debug("[TaskManager] Reset %d interrupted tasks", len(rows))
        except Exception:
            pass

    # ── Public API ────────────────────────────────────────────────────────

    def create(self, goal: str) -> AgentTask:
        """Create and queue a new task."""
        task = AgentTask(goal=goal, state=TaskState.QUEUED)
        with self._lock:
            self._tasks[task.task_id] = task
        self._save(task)
        logger.info("[TaskManager] Created task %s: %s", task.task_id, goal[:50])
        return task

    def get(self, task_id: str) -> Optional[AgentTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def set_state(self, task_id: str, state: TaskState, **kwargs) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task.state = state
            if state == TaskState.RUNNING and not task.started_at:
                task.started_at = time.time()
            if state in (TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED):
                task.completed_at = time.time()
            for k, v in kwargs.items():
                if hasattr(task, k):
                    setattr(task, k, v)
        self._save(task)

    def pause(self, task_id: str) -> bool:
        task = self.get(task_id)
        if task and task.state == TaskState.RUNNING:
            self.set_state(task_id, TaskState.PAUSED)
            logger.info("[TaskManager] Paused task %s", task_id)
            return True
        return False

    def resume(self, task_id: str) -> bool:
        task = self.get(task_id)
        if task and task.state == TaskState.PAUSED:
            self.set_state(task_id, TaskState.RUNNING)
            logger.info("[TaskManager] Resumed task %s", task_id)
            return True
        return False

    def cancel(self, task_id: str) -> bool:
        task = self.get(task_id)
        if task and task.state in (TaskState.RUNNING, TaskState.QUEUED, TaskState.PAUSED):
            self.set_state(task_id, TaskState.CANCELLED, error="User ne cancel kiya")
            logger.info("[TaskManager] Cancelled task %s", task_id)
            return True
        return False

    def list_active(self) -> List[AgentTask]:
        with self._lock:
            return [t for t in self._tasks.values()
                    if t.state in (TaskState.QUEUED, TaskState.RUNNING,
                                   TaskState.PAUSED, TaskState.WAITING_USER)]

    def list_recent(self, n: int = 10) -> List[AgentTask]:
        with self._lock:
            tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
            return tasks[:n]

    def find_by_keyword(self, keyword: str) -> Optional[AgentTask]:
        """Find the most recent task whose goal contains the keyword."""
        kw = keyword.lower()
        with self._lock:
            candidates = [t for t in self._tasks.values() if kw in t.goal.lower()]
            if not candidates:
                return None
            return max(candidates, key=lambda t: t.created_at)

    def status_summary(self) -> str:
        """Short Hindi status text for all active tasks."""
        active = self.list_active()
        if not active:
            return "Koi active task nahi hai."
        lines = []
        for t in active:
            icon = {"queued": "⏳", "running": "🔄", "paused": "⏸️",
                    "waiting_user": "❓"}.get(t.state.value, "•")
            lines.append(f"{icon} [{t.task_id}] {t.goal[:45]}")
        return "Active tasks:\n" + "\n".join(lines)


# Module-level singleton
task_manager = TaskManager()
