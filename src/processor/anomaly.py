"""
AI-Powered Anomaly Detection Engine for Laptop Health Monitoring.

Uses IsolationForest (multivariate) + Statistical methods (univariate: Z-score, EWMA)
for real-time anomaly detection on system metrics. Zero external API costs.
"""

import json
import pickle
import numpy as np
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import threading

# Optional sklearn import - graceful degradation if not available
try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    IsolationForest = None
    StandardScaler = None


class AnomalyEngine:
    """
    Hybrid anomaly detection combining:
    1. IsolationForest - multivariate, learns normal behavior patterns
    2. Z-score - univariate, catches sudden spikes
    3. EWMA - univariate, catches trend deviations
    """
    
    def __init__(self, config: Dict[str, Any], db_path: str = "data/monitor.db"):
        self.config = config.get("anomaly", {})
        self.enabled = self.config.get("enabled", True)
        self.db_path = db_path
        
        # Model parameters
        self.contamination = self.config.get("contamination", 0.05)
        self.min_training_samples = self.config.get("min_training_samples", 100)
        self.retrain_interval_hours = self.config.get("model_retrain_interval_hours", 6)
        self.zscore_threshold = self.config.get("zscore_threshold", 3.0)
        self.ewma_alpha = self.config.get("ewma_alpha", 0.3)
        
        # State
        self._model = None
        self._scaler = None
        self._feature_names: List[str] = []
        self._last_retrain: Optional[datetime] = None
        self._ewma_state: Dict[str, float] = {}  # metric_name -> ewma_value
        self._ewma_var: Dict[str, float] = {}    # metric_name -> ewma_variance
        self._lock = threading.Lock()
        
        # Metric categories to monitor for anomalies
        self.monitored_categories = [
            "cpu", "ram", "gpu", "storage", "battery", 
            "temps", "fans", "nvme", "network"
        ]
        
        # Initialize database tables
        self._init_anomaly_tables()
    
    def _init_anomaly_tables(self):
        """Create anomaly and prediction tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS anomalies (
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
                CREATE INDEX IF NOT EXISTS idx_anomalies_time ON anomalies(timestamp);
                CREATE INDEX IF NOT EXISTS idx_anomalies_component ON anomalies(component, severity);
                
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    predicted_health_score INTEGER,
                    risk_factors TEXT,
                    time_to_critical_hours REAL,
                    forecast_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_predictions_time ON predictions(timestamp);
            """)
    
    def _get_training_data(self, hours: int = 24) -> Tuple[np.ndarray, List[str]]:
        """
        Fetch recent metrics for training. Returns (features_array, feature_names).
        Only uses data from 'healthy' periods (no active CRITICAL issues).
        """
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT timestamp, category, metric_name, metric_value
                FROM metrics_history
                WHERE timestamp > ?
                ORDER BY timestamp ASC
            """, (cutoff,))
            rows = cursor.fetchall()
            
        if len(rows) < self.min_training_samples:
            return np.array([]), []
            
        # Group by timestamp in a single O(N) pass
        ts_map: Dict[str, Dict[str, float]] = {}
        all_features = set()
        for row in rows:
            ts = row["timestamp"]
            fn = f"{row['category']}.{row['metric_name']}"
            all_features.add(fn)
            if ts not in ts_map:
                ts_map[ts] = {}
            ts_map[ts][fn] = float(row["metric_value"])
            
        feature_names = sorted(all_features)
        if len(feature_names) < 3:
            return np.array([]), []
            
        # Cap to the most recent 500 timestamps for fast, lightweight training
        sorted_timestamps = sorted(ts_map.keys())[-500:]
        if len(sorted_timestamps) < self.min_training_samples:
            return np.array([]), []
            
        # Build matrix with forward-fill / last known value for missing keys
        last_values = {fn: 0.0 for fn in feature_names}
        matrix = []
        for ts in sorted_timestamps:
            row_dict = ts_map[ts]
            row_values = []
            for fn in feature_names:
                if fn in row_dict:
                    last_values[fn] = row_dict[fn]
                row_values.append(last_values[fn])
            matrix.append(row_values)
            
        X = np.array(matrix)
        return X, feature_names
    
    def _train_isolation_forest(self) -> bool:
        """Train IsolationForest model on recent healthy data."""
        # Always record attempt timestamp so we don't spam retries on every 30s run
        self._last_retrain = datetime.now()
        
        if not SKLEARN_AVAILABLE:
            return False
        
        X, feature_names = self._get_training_data()
        
        if X.size == 0 or X.shape[0] < self.min_training_samples:
            return False
        
        with self._lock:
            self._scaler = StandardScaler()
            X_scaled = self._scaler.fit_transform(X)
            
            self._model = IsolationForest(
                contamination=self.contamination,
                random_state=42,
                n_estimators=50,
                max_samples="auto",
                n_jobs=1
            )
            self._model.fit(X_scaled)
            self._feature_names = feature_names
            return True
    
    def _should_retrain(self) -> bool:
        if self._last_retrain is None:
            return True
        elapsed = datetime.now() - self._last_retrain
        return elapsed > timedelta(hours=self.retrain_interval_hours)
    
    def _detect_multivariate(self, current_metrics: Dict[str, Dict[str, float]]) -> List[Dict[str, Any]]:
        """Run IsolationForest detection on current metric vector."""
        if not SKLEARN_AVAILABLE or self._model is None or self._scaler is None:
            return []
        
        # Build feature vector in same order as training
        feature_vector = []
        for fn in self._feature_names:
            cat, metric = fn.split(".", 1)
            val = current_metrics.get(cat, {}).get(metric, 0.0)
            feature_vector.append(val)
        
        if len(feature_vector) != len(self._feature_names):
            return []
        
        X = np.array(feature_vector).reshape(1, -1)
        X_scaled = self._scaler.transform(X)
        
        # Get anomaly score (negative = more anomalous)
        score = self._model.score_samples(X_scaled)[0]
        # Convert to 0-1 scale (IsolationForest scores are typically -0.5 to 0.5)
        anomaly_score = max(0.0, min(1.0, 0.5 - score))
        
        if anomaly_score > self.contamination * 2:  # Threshold for flagging
            # Find which features contribute most (simplified: check individual z-scores)
            flagged = []
            for i, fn in enumerate(self._feature_names):
                cat, metric = fn.split(".", 1)
                val = feature_vector[i]
                # Get historical stats for this feature
                mean, std = self._get_feature_stats(cat, metric)
                if std > 0:
                    z = abs(val - mean) / std
                    if z > self.zscore_threshold:
                        flagged.append({
                            "component": cat.upper(),
                            "metric_name": metric,
                            "anomaly_score": float(anomaly_score),
                            "detection_method": "isolation_forest",
                            "metric_value": float(val),
                            "expected_range_min": float(mean - 3*std),
                            "expected_range_max": float(mean + 3*std),
                            "severity": self._score_to_severity(anomaly_score),
                            "details": json.dumps({"z_score": float(z), "feature_index": i})
                        })
            return flagged
        return []
    
    def _get_all_feature_stats(self, hours: int = 24) -> Dict[Tuple[str, str], Tuple[float, float]]:
        """Get mean and std for all metrics in a single indexed query."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        stats = {}
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            cursor = conn.execute("""
                SELECT category, metric_name, AVG(metric_value), AVG(metric_value * metric_value), COUNT(*)
                FROM metrics_history
                WHERE timestamp > ?
                GROUP BY category, metric_name
            """, (cutoff,))
            for cat, metric, avg_val, avg_sq, count in cursor.fetchall():
                if count >= 2:
                    mean = float(avg_val)
                    var = max(0.0, float(avg_sq) - (mean ** 2))
                    std = float(np.sqrt(var))
                    stats[(cat, metric)] = (mean, std)
        return stats

    def _get_feature_stats(self, category: str, metric: str, hours: int = 24) -> Tuple[float, float]:
        """Get mean and std for a single metric from recent history."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            cursor = conn.execute("""
                SELECT AVG(metric_value), AVG(metric_value * metric_value), COUNT(*)
                FROM metrics_history
                WHERE category = ? AND metric_name = ? AND timestamp > ?
            """, (category, metric, cutoff))
            row = cursor.fetchone()
            if row and row[2] and row[2] >= 2:
                mean = float(row[0])
                var = max(0.0, float(row[1]) - (mean ** 2))
                return mean, float(np.sqrt(var))
        return 0.0, 1.0
    
    def _detect_univariate_zscore(self, current_metrics: Dict[str, Dict[str, float]]) -> List[Dict[str, Any]]:
        """Z-score based univariate anomaly detection."""
        anomalies = []
        all_stats = self._get_all_feature_stats(hours=24)
        
        for category in self.monitored_categories:
            cat_metrics = current_metrics.get(category, {})
            for metric_name, value in cat_metrics.items():
                if not isinstance(value, (int, float)):
                    continue
                
                stat = all_stats.get((category, metric_name))
                if not stat:
                    continue
                mean, std = stat
                if std <= 0:
                    continue
                
                z_score = abs(value - mean) / std
                if z_score > self.zscore_threshold:
                    anomaly_score = min(1.0, z_score / 10.0)  # Normalize
                    anomalies.append({
                        "component": category.upper(),
                        "metric_name": metric_name,
                        "anomaly_score": float(anomaly_score),
                        "detection_method": "zscore",
                        "metric_value": float(value),
                        "expected_range_min": float(mean - 3*std),
                        "expected_range_max": float(mean + 3*std),
                        "severity": self._score_to_severity(anomaly_score),
                        "details": json.dumps({"z_score": float(z_score), "mean": float(mean), "std": float(std)})
                    })
        return anomalies
    
    def _detect_univariate_ewma(self, current_metrics: Dict[str, Dict[str, float]]) -> List[Dict[str, Any]]:
        """EWMA (Exponentially Weighted Moving Average) based detection."""
        anomalies = []
        alpha = self.ewma_alpha
        
        for category in self.monitored_categories:
            cat_metrics = current_metrics.get(category, {})
            for metric_name, value in cat_metrics.items():
                if not isinstance(value, (int, float)):
                    continue
                
                key = f"{category}.{metric_name}"
                
                if key not in self._ewma_state:
                    # Initialize with current value
                    self._ewma_state[key] = value
                    self._ewma_var[key] = 0.0
                    continue
                
                # Update EWMA
                prev_ewma = self._ewma_state[key]
                prev_var = self._ewma_var[key]
                
                new_ewma = alpha * value + (1 - alpha) * prev_ewma
                new_var = alpha * (value - new_ewma) ** 2 + (1 - alpha) * prev_var
                
                self._ewma_state[key] = new_ewma
                self._ewma_var[key] = new_var
                
                # Check deviation
                if new_var > 0:
                    std = np.sqrt(new_var)
                    z_score = abs(value - new_ewma) / std
                    if z_score > self.zscore_threshold:
                        anomaly_score = min(1.0, z_score / 10.0)
                        anomalies.append({
                            "component": category.upper(),
                            "metric_name": metric_name,
                            "anomaly_score": float(anomaly_score),
                            "detection_method": "ewma",
                            "metric_value": float(value),
                            "expected_range_min": float(new_ewma - 3*std),
                            "expected_range_max": float(new_ewma + 3*std),
                            "severity": self._score_to_severity(anomaly_score),
                            "details": json.dumps({
                                "z_score": float(z_score), 
                                "ewma": float(new_ewma), 
                                "ewma_var": float(new_var)
                            })
                        })
        return anomalies
    
    def _score_to_severity(self, score: float) -> str:
        """Convert anomaly score (0-1) to severity."""
        if score >= 0.8:
            return "CRITICAL"
        elif score >= 0.6:
            return "HIGH"
        elif score >= 0.4:
            return "WARNING"
        else:
            return "INFO"
    
    def analyze(self, current_metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Main entry point: run all detection methods on current metrics.
        Returns list of detected anomalies.
        """
        if not self.enabled:
            return []
        
        # Extract numeric metrics from collectors format
        numeric_metrics = {}
        for cat in self.monitored_categories:
            cat_data = current_metrics.get(cat, {})
            if isinstance(cat_data, dict):
                numeric_metrics[cat] = {
                    k: v for k, v in cat_data.items() 
                    if isinstance(v, (int, float))
                }
        
        # Retrain if needed
        if self._should_retrain():
            self._train_isolation_forest()
        
        all_anomalies = []
        
        # Run all detection methods
        all_anomalies.extend(self._detect_multivariate(numeric_metrics))
        all_anomalies.extend(self._detect_univariate_zscore(numeric_metrics))
        all_anomalies.extend(self._detect_univariate_ewma(numeric_metrics))
        
        # Deduplicate: keep highest severity per (component, metric)
        deduped = {}
        for a in all_anomalies:
            key = (a["component"], a["metric_name"])
            if key not in deduped or self._severity_rank(a["severity"]) > self._severity_rank(deduped[key]["severity"]):
                deduped[key] = a
        
        # Add timestamp
        timestamp = datetime.now().isoformat()
        for a in deduped.values():
            a["timestamp"] = timestamp
        
        # Store in database
        self._store_anomalies(list(deduped.values()))
        
        return list(deduped.values())
    
    def _severity_rank(self, severity: str) -> int:
        return {"CRITICAL": 4, "HIGH": 3, "WARNING": 2, "INFO": 1}.get(severity, 0)
    
    def _store_anomalies(self, anomalies: List[Dict[str, Any]]):
        """Persist anomalies to database."""
        if not anomalies:
            return
        
        with sqlite3.connect(self.db_path) as conn:
            for a in anomalies:
                conn.execute("""
                    INSERT INTO anomalies 
                    (timestamp, component, metric_name, anomaly_score, detection_method,
                     metric_value, expected_range_min, expected_range_max, severity, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    a["timestamp"], a["component"], a["metric_name"],
                    a["anomaly_score"], a["detection_method"],
                    a["metric_value"], a["expected_range_min"], a["expected_range_max"],
                    a["severity"], a["details"]
                ))
    
    def get_recent_anomalies(self, hours: int = 24, severity: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve recent anomalies from database."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if severity:
                cursor = conn.execute("""
                    SELECT * FROM anomalies 
                    WHERE datetime(timestamp) > datetime(?) AND severity = ?
                    ORDER BY timestamp DESC
                """, (cutoff, severity))
            else:
                cursor = conn.execute("""
                    SELECT * FROM anomalies 
                    WHERE datetime(timestamp) > datetime(?)
                    ORDER BY timestamp DESC
                """, (cutoff,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_anomaly_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get anomaly statistics for dashboard."""
        anomalies = self.get_recent_anomalies(hours)
        
        by_severity = {}
        by_component = {}
        by_method = {}
        
        for a in anomalies:
            by_severity[a["severity"]] = by_severity.get(a["severity"], 0) + 1
            by_component[a["component"]] = by_component.get(a["component"], 0) + 1
            by_method[a["detection_method"]] = by_method.get(a["detection_method"], 0) + 1
        
        return {
            "total": len(anomalies),
            "by_severity": by_severity,
            "by_component": by_component,
            "by_method": by_method,
            "latest": anomalies[0] if anomalies else None
        }
    
    def save_model(self, path: str = "data/anomaly_model.pkl"):
        """Persist trained model to disk."""
        if self._model is not None and self._scaler is not None:
            with open(path, "wb") as f:
                pickle.dump({
                    "model": self._model,
                    "scaler": self._scaler,
                    "feature_names": self._feature_names,
                    "last_retrain": self._last_retrain,
                    "ewma_state": self._ewma_state,
                    "ewma_var": self._ewma_var
                }, f)
    
    def load_model(self, path: str = "data/anomaly_model.pkl"):
        """Load trained model from disk."""
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
            self._model = data["model"]
            self._scaler = data["scaler"]
            self._feature_names = data["feature_names"]
            self._last_retrain = data["last_retrain"]
            self._ewma_state = data.get("ewma_state", {})
            self._ewma_var = data.get("ewma_var", {})
            return True
        except Exception:
            return False


def create_anomaly_engine(config: Dict[str, Any], db_path: str = "data/monitor.db") -> AnomalyEngine:
    """Factory function for creating AnomalyEngine instance."""
    engine = AnomalyEngine(config, db_path)
    # Try to load existing model
    engine.load_model()
    return engine