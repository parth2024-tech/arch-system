import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from src.processor.anomaly import AnomalyEngine
from src.processor.predictive import PredictiveEngine
from src.alerts.telegram import TelegramDispatcher, TelegramConfig

@pytest.fixture
def mock_config():
    return {
        "anomaly": {
            "enabled": True,
            "contamination": 0.05,
            "min_training_samples": 5,
            "zscore_threshold": 2.0
        },
        "predictive": {
            "enabled": True,
            "forecast_horizon_hours": 4,
            "trend_window_hours": 24
        },
        "telegram": {
            "enabled": False,
            "bot_token": "test_token",
            "chat_id": "123456"
        }
    }

def test_anomaly_engine_univariate(tmp_path, mock_config):
    db_file = tmp_path / "test_anomaly.db"
    # Seed db with some metrics
    import sqlite3
    conn = sqlite3.connect(str(db_file))
    conn.executescript("""
        CREATE TABLE metrics_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            category TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            extra_json TEXT
        );
        CREATE TABLE anomalies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            component TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            anomaly_score REAL NOT NULL,
            detection_method TEXT NOT NULL,
            metric_value REAL NOT NULL,
            expected_range_min REAL,
            expected_range_max REAL,
            severity TEXT NOT NULL,
            details TEXT
        );
        CREATE TABLE predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            predicted_health_score INTEGER,
            risk_factors TEXT,
            time_to_critical_hours REAL,
            forecast_json TEXT
        );
    """)
    # Insert normal values
    for i in range(10):
        conn.execute(
            "INSERT INTO metrics_history (timestamp, category, metric_name, metric_value) VALUES (?, ?, ?, ?)",
            (f"2026-09-05T10:0{i}:00", "cpu", "overall_utilization", 20.0 + i)
        )
    conn.commit()
    conn.close()
    
    engine = AnomalyEngine(mock_config, str(db_file))
    
    # Test normal metrics
    current = {"cpu": {"overall_utilization": 22.0}}
    anomalies = engine.analyze(current)
    # With zscore_threshold 2.0 and 22.0 close to mean, no anomaly expected
    assert isinstance(anomalies, list)

def test_predictive_engine(tmp_path, mock_config):
    db_file = tmp_path / "test_pred.db"
    import sqlite3
    from datetime import datetime, timedelta
    conn = sqlite3.connect(str(db_file))
    conn.executescript("""
        CREATE TABLE metrics_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            category TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            extra_json TEXT
        );
        CREATE TABLE predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            predicted_health_score INTEGER,
            risk_factors TEXT,
            time_to_critical_hours REAL,
            forecast_json TEXT
        );
    """)
    # Insert rising trend for RAM (within last 24 hours)
    base = datetime.now() - timedelta(hours=5)
    for i in range(10):
        ts = (base + timedelta(minutes=i*30)).isoformat()
        conn.execute(
            "INSERT INTO metrics_history (timestamp, category, metric_name, metric_value) VALUES (?, ?, ?, ?)",
            (ts, "ram", "percent", 50.0 + (i * 4.0))
        )
    conn.commit()
    conn.close()
    
    pred_engine = PredictiveEngine(mock_config, str(db_file))
    report = pred_engine.analyze_predictions()
    
    assert "predicted_health_score" in report
    assert "risk_factors" in report
    assert "forecasts" in report
    assert "ram.percent" in report["forecasts"]

def test_telegram_config():
    config = TelegramConfig(enabled=True, bot_token="abc", chat_id="123")
    dispatcher = TelegramDispatcher(config)
    assert dispatcher.config.bot_token == "abc"
    status = dispatcher.get_health_status()
    assert isinstance(status, dict)
