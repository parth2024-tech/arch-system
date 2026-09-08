import json
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

class AlertManager:
    def __init__(self, config: Dict[str, Any]):
        self.enabled = config.get("enabled", True)
        self.deduplicate_window = config.get("deduplicate_window_seconds", 300)
        self.last_alerts: Dict[str, float] = {}

    def should_alert(self, issue: Dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        
        # Create a key for deduplication
        key = f"{issue['component']}:{issue['title']}"
        now = time.time()
        
        if key in self.last_alerts:
            if now - self.last_alerts[key] < self.deduplicate_window:
                return False
        
        self.last_alerts[key] = now
        return True

    def format_alert(self, issue: Dict[str, Any]) -> str:
        severity_emoji = {
            "CRITICAL": "🔴",
            "HIGH": "🟠",
            "WARNING": "🟡",
            "INFO": "🔵"
        }
        emoji = severity_emoji.get(issue["severity"], "⚪")
        
        return (
            f"{emoji} **{issue['severity']}: {issue['title']}**\n"
            f"**Component:** {issue['component']}\n"
            f"**Time:** {issue.get('timestamp', datetime.now().isoformat())}\n"
            f"**Description:** {issue['description']}\n"
            f"**Evidence:** {issue.get('evidence', 'N/A')}\n"
            f"**Recommendation:** {issue.get('recommendation', 'N/A')}\n"
        )

    def dispatch(self, issue: Dict[str, Any]) -> bool:
        if not self.should_alert(issue):
            return False
        
        alert_text = self.format_alert(issue)
        print(f"ALERT:\n{alert_text}")  # Console output
        
        # Could add webhook/Telegram dispatch here
        return True

    def dispatch_batch(self, issues: List[Dict[str, Any]]) -> int:
        dispatched = 0
        for issue in issues:
            if self.dispatch(issue):
                dispatched += 1
        return dispatched