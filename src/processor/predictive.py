"""
Predictive Health Scoring and Trend Forecasting Engine.

Uses linear regression on recent time-series metrics (CPU temp, RAM %, disk %, battery)
to forecast future values and calculate risk scores and time-to-critical estimates.
"""

import numpy as np
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple


class PredictiveEngine:
    """
    Forecasting & Risk Scoring Engine:
    - Linear regression on metric time-series
    - Forecast horizon estimation (1-24 hours)
    - Time-to-critical threshold calculation
    - Overall predictive risk scoring (0-100)
    """
    
    def __init__(self, config: Dict[str, Any], db_path: str = "data/monitor.db"):
        self.config = config.get("predictive", {})
        self.enabled = self.config.get("enabled", True)
        self.thresholds = config.get("thresholds", {})
        self.db_path = db_path
        
        self.forecast_horizon_hours = self.config.get("forecast_horizon_hours", 4)
        self.trend_window_hours = self.config.get("trend_window_hours", 24)
        self.risk_threshold = self.config.get("risk_threshold", 60)
    
    def _fetch_trend_data(self, category: str, metric_name: str, hours: int = 24) -> List[Tuple[float, float]]:
        """Fetch time-series data as (epoch_seconds, value) pairs."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            cursor = conn.execute("""
                SELECT timestamp, metric_value FROM metrics_history
                WHERE category = ? AND metric_name = ? AND timestamp > ?
                ORDER BY timestamp ASC
            """, (category, metric_name, cutoff))
            
            rows = cursor.fetchall()
            
        if len(rows) < 5:
            return []
            
        # Downsample if history is dense (> 300 points) to keep regression instant
        if len(rows) > 300:
            step = max(1, len(rows) // 300)
            rows = rows[::step]

        data = []
        for row in rows:
            try:
                dt = datetime.fromisoformat(row[0])
                epoch = dt.timestamp()
                data.append((epoch, float(row[1])))
            except Exception:
                continue
                
        return data
    
    def _calculate_linear_trend(self, points: List[Tuple[float, float]]) -> Tuple[float, float, float]:
        """
        Calculate linear regression: y = mx + c.
        Returns (slope_per_hour, intercept, r_squared).
        """
        if len(points) < 5:
            return 0.0, 0.0, 0.0
            
        x = np.array([p[0] for p in points])
        y = np.array([p[1] for p in points])
        
        # Convert x to hours relative to start
        x = (x - x[0]) / 3600.0
        
        if np.all(x == x[0]):
            return 0.0, float(y[0]), 0.0
            
        # Least squares fit
        coeffs = np.polyfit(x, y, 1, full=False)
        m, c = coeffs[0], coeffs[1]
        
        # Calculate R-squared
        p = np.poly1d(coeffs)
        yhat = p(x)
        ybar = np.mean(y)
        ssreg = np.sum((yhat - ybar) ** 2)
        sstot = np.sum((y - ybar) ** 2)
        
        r2 = ssreg / sstot if sstot > 0 else 0.0
        
        return float(m), float(c), float(max(0.0, min(1.0, r2)))
    
    def analyze_predictions(self) -> Dict[str, Any]:
        """
        Analyze trends for critical metrics and forecast future state.
        Returns prediction report with risk factors and time-to-critical.
        """
        if not self.enabled:
            return {"predicted_health_score": 100, "risk_factors": [], "forecasts": {}}
            
        metrics_to_watch = [
            ("cpu", "overall_utilization", 100.0, "CPU Utilization"),
            ("ram", "percent", 95.0, "RAM Utilization"),
            ("storage", "percent", 95.0, "Disk Utilization"),
            ("battery", "percent", 10.0, "Battery Level"),
        ]
        
        risk_factors = []
        forecasts = {}
        min_time_to_critical = float('inf')
        health_penalty = 0
        
        for category, metric, critical_limit, label in metrics_to_watch:
            points = self._fetch_trend_data(category, metric, self.trend_window_hours)
            if not points:
                continue
                
            slope, intercept, r2 = self._calculate_linear_trend(points)
            current_val = points[-1][1]
            
            # Forecast value at horizon
            forecast_val = current_val + (slope * self.forecast_horizon_hours)
            
            forecasts[f"{category}.{metric}"] = {
                "label": label,
                "current": current_val,
                "forecast": forecast_val,
                "slope_per_hour": slope,
                "r_squared": r2
            }
            
            # Check if trending toward critical
            is_increasing = slope > 0 if critical_limit > 50 else slope < 0
            
            if is_increasing and r2 > 0.3:
                # Calculate time to critical
                if slope != 0:
                    hours_to_limit = (critical_limit - current_val) / slope
                    if 0 < hours_to_limit <= 48:
                        min_time_to_critical = min(min_time_to_critical, hours_to_limit)
                        risk_factors.append({
                            "component": category.upper(),
                            "metric": metric,
                            "label": label,
                            "current": current_val,
                            "forecast": forecast_val,
                            "slope_per_hour": slope,
                            "r_squared": r2,
                            "hours_to_critical": round(hours_to_limit, 1),
                            "severity": "HIGH" if hours_to_limit < 6 else "WARNING"
                        })
                        health_penalty += int(30 / hours_to_limit)
                        
        predicted_score = max(0, 100 - health_penalty)
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "predicted_health_score": predicted_score,
            "risk_factors": risk_factors,
            "time_to_critical_hours": round(min_time_to_critical, 1) if min_time_to_critical != float('inf') else None,
            "forecasts": forecasts
        }
        
        # Store in database
        self._store_prediction(report)
        
        return report
    
    def _store_prediction(self, report: Dict[str, Any]):
        """Persist prediction report to database."""
        import json
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO predictions 
                (timestamp, predicted_health_score, risk_factors, time_to_critical_hours, forecast_json)
                VALUES (?, ?, ?, ?, ?)
            """, (
                report["timestamp"],
                report["predicted_health_score"],
                json.dumps(report["risk_factors"]),
                report["time_to_critical_hours"],
                json.dumps(report["forecasts"])
            ))
    
    def get_recent_predictions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve recent prediction history."""
        import json
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM predictions 
                ORDER BY timestamp DESC LIMIT ?
            """, (limit,))
            
            results = []
            for row in cursor.fetchall():
                d = dict(row)
                d["risk_factors"] = json.loads(d["risk_factors"] or "[]")
                d["forecasts"] = json.loads(d["forecast_json"] or "{}")
                results.append(d)
            return results


def create_predictive_engine(config: Dict[str, Any], db_path: str = "data/monitor.db") -> PredictiveEngine:
    """Factory function for PredictiveEngine."""
    return PredictiveEngine(config, db_path)