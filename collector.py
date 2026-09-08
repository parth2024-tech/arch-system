#!/usr/bin/env python3
"""
Background collector for laptop health monitoring.
Runs via systemd timer every 30 seconds.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import tomli
import asyncio
from datetime import datetime

from storage.database import Database
from collectors.hardware import HardwareCollector
from collectors.os_collector import OSCollector
from collectors.process_collector import ProcessCollector
from collectors.network_collector import NetworkCollector
from processor.diagnostics import DiagnosticEngine
from processor.anomaly import create_anomaly_engine
from processor.predictive import create_predictive_engine
from alerts.telegram import create_telegram_dispatcher


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


def calculate_health_score(issues):
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
    return max(0, 100 - deduction)


def main():
    # Load config
    with open("config/monitor.toml", "rb") as f:
        config = tomli.load(f)

    db = Database(config["monitor"]["db_path"])
    engine = DiagnosticEngine(config["thresholds"])
    anomaly_engine = create_anomaly_engine(config, config["monitor"]["db_path"])
    predictive_engine = create_predictive_engine(config, config["monitor"]["db_path"])
    telegram_dispatcher = create_telegram_dispatcher(config)

    # Collect all metrics
    data = collect_all()
    timestamp = datetime.now().isoformat()

    # Store metrics in database (batch insert in single transaction)
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

    # Run diagnostic engine
    issues = engine.analyze(
        data["cpu"], data["ram"], data["gpu"], data["storage"],
        data["battery"], data["temps"], data["fans"], data["os"],
        data["processes"], data["network"], data["nvme"]
    )

    # Run anomaly detection
    anomalies = anomaly_engine.analyze(data)

    # Run predictive analysis
    predictions = predictive_engine.analyze_predictions()

    # Combine issues with anomalies
    all_issues = issues + anomalies
    health_score = calculate_health_score(all_issues)

    # Synchronize issues with database (deduplication & auto-resolution)
    db.sync_active_issues(issues, timestamp)

    # Send Telegram alerts for HIGH/CRITICAL issues
    critical_issues = [i for i in all_issues if i["severity"] in ["HIGH", "CRITICAL"]]
    if critical_issues and telegram_dispatcher.config.enabled:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        sent = loop.run_until_complete(telegram_dispatcher.dispatch_batch(critical_issues))
        if sent > 0:
            print(f"Sent {sent} Telegram alert(s)")

    # Purge old data
    db.purge_old_data(config["monitor"]["retention_days"])

    print(f"Collection complete: health={health_score}, issues={len(all_issues)}, anomalies={len(anomalies)}")


if __name__ == "__main__":
    main()
