import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from src.storage.database import Database

def test_database_creation(tmp_path):
    db_file = tmp_path / "test.db"
    db = Database(str(db_file))
    db.insert_metric("2026-09-05T18:00:00", "cpu", "utilization", 25.5)
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM metrics_history")
    row = cursor.fetchone()
    assert row["metric_name"] == "utilization"
    assert row["metric_value"] == 25.5

def test_database_wal_mode(tmp_path):
    db_file = tmp_path / "test_wal.db"
    db = Database(str(db_file))
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    assert mode == "wal"

def test_database_purge(tmp_path):
    db_file = tmp_path / "test_purge.db"
    db = Database(str(db_file))
    db.insert_metric("2020-01-01T00:00:00", "cpu", "utilization", 10.0)
    db.insert_metric("2026-09-05T18:00:00", "cpu", "utilization", 25.5)
    db.purge_old_data(days=7)
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM metrics_history")
    assert cursor.fetchone()["cnt"] == 1

def test_database_issues(tmp_path):
    db_file = tmp_path / "test_issues.db"
    db = Database(str(db_file))
    issue_id = db.insert_issue(
        "2026-09-05T18:00:00", "RAM", "HIGH", "Test Issue", "Description", "Evidence", "Recommendation"
    )
    assert issue_id > 0
    
    issues = db.get_active_issues()
    assert len(issues) == 1
    assert issues[0]["title"] == "Test Issue"
    assert issues[0]["severity"] == "HIGH"

def test_database_insert_metrics_batch(tmp_path):
    db_file = tmp_path / "test_batch.db"
    db = Database(str(db_file))
    rows = [
        ("2026-09-05T18:00:00", "cpu", "utilization", 25.5, None),
        ("2026-09-05T18:00:00", "ram", "percent", 60.2, None),
        ("2026-09-05T18:00:00", "temps", "core_0", 45.0, None),
    ]
    db.insert_metrics_batch(rows)
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM metrics_history")
    assert cursor.fetchone()["cnt"] == 3

def test_database_sync_active_issues(tmp_path):
    db_file = tmp_path / "test_sync.db"
    db = Database(str(db_file))
    
    # Tick 1: 2 issues
    t1 = "2026-09-07T11:00:00"
    issues_t1 = [
        {"component": "CPU", "severity": "WARNING", "title": "Elevated Temp", "description": "High", "evidence": "85C"},
        {"component": "KERNEL", "severity": "WARNING", "title": "Kernel Err", "description": "ACPI", "evidence": "log1"},
    ]
    db.sync_active_issues(issues_t1, t1)
    active = db.get_active_issues()
    assert len(active) == 2
    assert active[0]["recurring_count"] == 1

    # Tick 2: Kernel Err recurs, Elevated Temp cleared
    t2 = "2026-09-07T11:00:30"
    issues_t2 = [
        {"component": "KERNEL", "severity": "WARNING", "title": "Kernel Err", "description": "ACPI", "evidence": "log2"},
    ]
    db.sync_active_issues(issues_t2, t2)
    active = db.get_active_issues()
    assert len(active) == 1
    assert active[0]["title"] == "Kernel Err"
    assert active[0]["recurring_count"] == 2
    assert active[0]["evidence"] == "log2"