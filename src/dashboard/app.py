from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os
import sys
import tomli
from datetime import datetime
from typing import List, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.storage.database import Database
from src.collectors.hardware import HardwareCollector
from src.collectors.os_collector import OSCollector
from src.collectors.process_collector import ProcessCollector
from src.collectors.network_collector import NetworkCollector
from src.processor.diagnostics import DiagnosticEngine
from src.processor.anomaly import create_anomaly_engine
from src.processor.predictive import create_predictive_engine
from src.alerts.telegram import create_telegram_dispatcher

app = FastAPI(title="Laptop Health Monitor")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Load config
with open("config/monitor.toml", "rb") as f:
    config = tomli.load(f)

db = Database(config["monitor"]["db_path"])
engine = DiagnosticEngine(config["thresholds"])
anomaly_engine = create_anomaly_engine(config, config["monitor"]["db_path"])
predictive_engine = create_predictive_engine(config, config["monitor"]["db_path"])
telegram_dispatcher = create_telegram_dispatcher(config)

def collect_all():
    """Collect all metrics from all collectors."""
    return {
        "cpu": HardwareCollector.collect_cpu(),
        "ram": HardwareCollector.collect_ram(),
        "gpu": HardwareCollector.collect_gpu(),
        "storage": HardwareCollector.collect_storage(),
        "battery": HardwareCollector.collect_battery(),
        "temps": HardwareCollector.collect_temperatures(),
        "fans": HardwareCollector.collect_fans(),
        "nvme": HardwareCollector.collect_nvme_health(),
        "os": {
            "failed_services": OSCollector.get_failed_services(),
            "kernel_errors": OSCollector.get_recent_kernel_errors(),
        },
        "processes": {
            "top": ProcessCollector.get_top_processes(5),
            "memory_hogs": ProcessCollector.get_memory_hogs(5),
            "zombies": ProcessCollector.get_zombie_processes(),
        },
        "network": NetworkCollector.check_connectivity(),
    }

def calculate_health_score(issues: List[Dict[str, Any]]) -> int:
    """Calculate a health score from 0-100 based on active issues."""
    if not issues:
        return 100
    
    severity_weights = {
        "CRITICAL": 30,
        "HIGH": 20,
        "WARNING": 10,
        "INFO": 2
    }
    
    deduction = sum(severity_weights.get(issue["severity"], 0) for issue in issues)
    score = max(0, 100 - deduction)
    return score

def get_component_status(issues: List[Dict[str, Any]], component: str) -> str:
    """Get status for a specific component."""
    comp_issues = [i for i in issues if i["component"] == component]
    if not comp_issues:
        return "HEALTHY"
    severities = [i["severity"] for i in comp_issues]
    if "CRITICAL" in severities:
        return "CRITICAL"
    elif "HIGH" in severities:
        return "HIGH"
    elif "WARNING" in severities:
        return "WARNING"
    elif "INFO" in severities:
        return "INFO"
    return "HEALTHY"

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )

@app.get("/api/status")
def api_status(request: Request):
    data = collect_all()
    issues = engine.analyze(
        data["cpu"], data["ram"], data["gpu"], data["storage"],
        data["battery"], data["temps"], data["fans"], data["os"],
        data["processes"], data["network"], data["nvme"]
    )
    
    # Run anomaly detection
    anomalies = anomaly_engine.analyze(data)
    
    # Run predictive analysis
    predictions = predictive_engine.analyze_predictions()
    
    # Combine issues with anomalies for health scoring
    all_issues = issues + anomalies
    health_score = calculate_health_score(all_issues)
    
    # Store metrics in database (batch insert)
    timestamp = datetime.now().isoformat()
    metric_rows = []
    for category, metrics in data.items():
        if isinstance(metrics, dict):
            if category in ["cpu", "ram", "gpu", "storage", "battery", "temps", "fans", "nvme", "network"]:
                for k, v in metrics.items():
                    if isinstance(v, (int, float)):
                        metric_rows.append((timestamp, category, k, float(v), None))
            elif category == "os":
                for k, v in metrics.items():
                    if isinstance(v, list):
                        metric_rows.append((timestamp, category, k, float(len(v)), None))
    db.insert_metrics_batch(metric_rows)
    
    # Store issues
    for issue in issues:
        db.insert_issue(
            timestamp, issue["component"], issue["severity"],
            issue["title"], issue["description"],
            issue.get("evidence", ""), issue.get("recommendation", "")
        )
    
    # Format component statuses
    components = [
        "CPU", "RAM", "GPU", "STORAGE", "THERMALS", 
        "BATTERY", "KERNEL", "SERVICES", "NETWORK", "PROCESSES"
    ]
    component_status = {c: get_component_status(all_issues, c) for c in components}
    
    # Send Telegram alerts for HIGH/CRITICAL issues (including anomalies)
    critical_issues = [i for i in all_issues if i["severity"] in ["HIGH", "CRITICAL"]]
    if critical_issues:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(telegram_dispatcher.dispatch_batch(critical_issues))
    
    # Return template response
    return templates.TemplateResponse(
        request=request,
        name="_status.html",
        context={
            "health_score": health_score,
            "predicted_health_score": predictions.get("predicted_health_score", health_score),
            "timestamp": timestamp,
            "components": component_status,
            "predictions": predictions,
            "metrics": {
                "cpu": data["cpu"],
                "ram": data["ram"],
                "gpu": data["gpu"],
                "storage": data["storage"],
                "battery": data["battery"],
                "temps": data["temps"],
                "fans": data["fans"],
                "nvme": data["nvme"],
                "network": data["network"],
            }
        }
    )

@app.get("/api/history")
def api_history(category: str = "cpu", metric: str = "overall_utilization", limit: int = 60):
    data = db.get_recent_metrics(category, metric, limit)
    return {"data": list(reversed(data))}

@app.get("/api/issues")
def api_issues(request: Request):
    issues = db.get_active_issues()
    return templates.TemplateResponse(
        request=request,
        name="_issues.html",
        context={"issues": issues}
    )

@app.get("/api/anomalies")
def api_anomalies(request: Request, hours: int = 24, severity: str = ""):
    anomalies = anomaly_engine.get_recent_anomalies(hours, severity if severity else None)
    summary = anomaly_engine.get_anomaly_summary(hours)
    return templates.TemplateResponse(
        request=request,
        name="_anomalies.html",
        context={"anomalies": anomalies, "summary": summary}
    )

@app.get("/api/predictions")
def api_predictions(request: Request, limit: int = 10):
    predictions = predictive_engine.get_recent_predictions(limit)
    return templates.TemplateResponse(
        request=request,
        name="_predictions.html",
        context={"predictions": predictions}
    )

@app.get("/api/telegram/health")
def api_telegram_health(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="_telegram_status.html",
        context={"telegram": telegram_dispatcher.health_check_sync()}
    )

@app.post("/api/telegram/test")
def api_telegram_test(request: Request):
    """Send a test message to verify Telegram integration."""
    import asyncio
    test_issue = {
        "component": "TEST",
        "severity": "INFO",
        "title": "Test Alert from HERMES Monitor",
        "description": "This is a test message to verify Telegram bot integration.",
        "evidence": "Manual test trigger",
        "recommendation": "No action needed",
        "timestamp": datetime.now().isoformat()
    }
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    success = loop.run_until_complete(telegram_dispatcher.dispatch(test_issue, force=True))
    return {"success": success}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)