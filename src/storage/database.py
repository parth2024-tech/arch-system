import sqlite3
import os
from typing import List, Dict, Any, Optional, Tuple

class Database:
    def __init__(self, db_path: str = "data/monitor.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        with self.get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS metrics_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    category TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    extra_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_metrics_time ON metrics_history(timestamp);
                CREATE INDEX IF NOT EXISTS idx_metrics_cat ON metrics_history(category, metric_name);

                CREATE TABLE IF NOT EXISTS issues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    component TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    evidence TEXT,
                    recommendation TEXT,
                    status TEXT DEFAULT 'active',
                    recurring_count INTEGER DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status, severity);

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    details TEXT
                );
            """)

    def insert_metric(self, timestamp: str, category: str, name: str, value: float, extra: Optional[str] = None):
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO metrics_history (timestamp, category, metric_name, metric_value, extra_json) VALUES (?, ?, ?, ?, ?)",
                (timestamp, category, name, value, extra)
            )

    def insert_metrics_batch(self, rows: List[Tuple[str, str, str, float, Optional[str]]]):
        """Batch insert metrics within a single transaction."""
        if not rows:
            return
        with self.get_connection() as conn:
            conn.executemany(
                "INSERT INTO metrics_history (timestamp, category, metric_name, metric_value, extra_json) VALUES (?, ?, ?, ?, ?)",
                rows
            )

    def purge_old_data(self, days: int = 7):
        with self.get_connection() as conn:
            conn.execute(
                "DELETE FROM metrics_history WHERE datetime(timestamp) < datetime('now', '-' || ? || ' days')",
                (days,)
            )

    def get_recent_metrics(self, category: str, metric_name: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT timestamp, metric_value, extra_json FROM metrics_history WHERE category = ? AND metric_name = ? ORDER BY timestamp DESC LIMIT ?",
                (category, metric_name, limit)
            )
            return [dict(row) for row in cursor.fetchall()]

    def insert_issue(self, timestamp: str, component: str, severity: str, title: str, description: str, 
                     evidence: str = "", recommendation: str = "") -> int:
        with self.get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO issues (timestamp, component, severity, title, description, evidence, recommendation)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (timestamp, component, severity, title, description, evidence, recommendation)
            )
            return cursor.lastrowid or 0

    def sync_active_issues(self, current_issues: List[Dict[str, Any]], timestamp: str):
        """Synchronize active issues with deduplication and auto-resolution."""
        current_keys = set()
        with self.get_connection() as conn:
            for issue in current_issues:
                component = issue["component"]
                severity = issue["severity"]
                title = issue["title"]
                description = issue["description"]
                evidence = issue.get("evidence", "")
                recommendation = issue.get("recommendation", "")
                current_keys.add((component, title))

                # Check if there are already active issues with this component and title
                cursor = conn.execute(
                    "SELECT id, recurring_count FROM issues WHERE component = ? AND title = ? AND status = 'active' ORDER BY id DESC",
                    (component, title)
                )
                existing_rows = cursor.fetchall()
                if existing_rows:
                    latest = existing_rows[0]
                    # Update existing active issue
                    conn.execute(
                        """UPDATE issues
                           SET timestamp = ?, severity = ?, description = ?, evidence = ?, recommendation = ?, recurring_count = recurring_count + 1
                           WHERE id = ?""",
                        (timestamp, severity, description, evidence, recommendation, latest["id"])
                    )
                    # Clean up any older duplicate active rows for the same issue
                    for old_row in existing_rows[1:]:
                        conn.execute("UPDATE issues SET status = 'resolved' WHERE id = ?", (old_row["id"],))
                else:
                    # Insert new active issue
                    conn.execute(
                        """INSERT INTO issues (timestamp, component, severity, title, description, evidence, recommendation, status, recurring_count)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 1)""",
                        (timestamp, component, severity, title, description, evidence, recommendation)
                    )

            # Auto-resolve any active issues that are no longer present in current_issues
            cursor = conn.execute("SELECT id, component, title FROM issues WHERE status = 'active'")
            active_rows = cursor.fetchall()
            for row in active_rows:
                if (row["component"], row["title"]) not in current_keys:
                    conn.execute(
                        "UPDATE issues SET status = 'resolved' WHERE id = ?",
                        (row["id"],)
                    )

    def clean_stale_duplicates(self):
        """Resolve all stale duplicate active issues, keeping at most one latest active issue per (component, title)."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT id, component, title FROM issues WHERE status = 'active' ORDER BY id DESC")
            seen = set()
            to_resolve = []
            for row in cursor.fetchall():
                key = (row["component"], row["title"])
                if key in seen:
                    to_resolve.append(row["id"])
                else:
                    seen.add(key)
            if to_resolve:
                conn.executemany("UPDATE issues SET status = 'resolved' WHERE id = ?", [(i,) for i in to_resolve])

    def get_active_issues(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM issues WHERE status = 'active' ORDER BY severity DESC, timestamp DESC LIMIT ?",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def log_audit(self, timestamp: str, action: str, details: str = ""):
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO audit_log (timestamp, action, details) VALUES (?, ?, ?)",
                (timestamp, action, details)
            )