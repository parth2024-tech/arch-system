"""
Telegram Alert Dispatcher for Laptop Health Monitoring.

Async HTTP client using httpx for zero-cost Telegram Bot API integration.
Supports MarkdownV2 formatting, deduplication, rate limiting, and health checks.
"""

import asyncio
import httpx
import json
import time
import os
from datetime import datetime
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TelegramConfig:
    """Telegram bot configuration."""
    enabled: bool = True
    bot_token: str = ""
    chat_id: str = ""
    parse_mode: str = "MarkdownV2"
    disable_notification: bool = False
    alert_severities: List[str] = field(default_factory=lambda: ["HIGH", "CRITICAL"])
    max_retries: int = 3
    retry_delay: float = 1.0
    rate_limit_per_minute: int = 20
    
    def __post_init__(self):
        # Allow env var override
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", self.bot_token)
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", self.chat_id)


class TelegramDispatcher:
    """
    Handles Telegram alert dispatch with:
    - Async HTTP via httpx
    - MarkdownV2 escaping
    - Severity-based filtering
    - Rate limiting & deduplication
    - Retry with exponential backoff
    - Health check endpoint
    """
    
    BASE_URL = "https://api.telegram.org/bot"
    
    def __init__(self, config: TelegramConfig):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._last_sent: Dict[str, float] = {}  # deduplication key -> timestamp
        self._sent_count = 0
        self._sent_window_start = time.time()
        self._lock = asyncio.Lock()
        self._health_status = {"ok": False, "last_check": None, "error": None}
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0),
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=2)
            )
        return self._client
    
    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    def _escape_markdown_v2(self, text: str) -> str:
        """Escape special characters for Telegram MarkdownV2."""
        # Characters that need escaping in MarkdownV2
        escape_chars = r'_*[]()~`>#+-=|{}.!'
        return ''.join(f'\\{c}' if c in escape_chars else c for c in text)
    
    def _format_alert(self, issue: Dict[str, Any]) -> str:
        """Format issue as Telegram MarkdownV2 message."""
        severity = issue.get("severity", "INFO")
        component = issue.get("component", "UNKNOWN")
        title = issue.get("title", "Alert")
        description = issue.get("description", "")
        evidence = issue.get("evidence", "")
        recommendation = issue.get("recommendation", "")
        timestamp = issue.get("timestamp", datetime.now().isoformat())
        
        # Severity emoji mapping
        severity_emoji = {
            "CRITICAL": "🔴",
            "HIGH": "🟠", 
            "WARNING": "🟡",
            "INFO": "🔵",
            "LOW": "⚪"
        }
        emoji = severity_emoji.get(severity, "⚪")
        
        # Escape all user content
        safe_title = self._escape_markdown_v2(title)
        safe_component = self._escape_markdown_v2(component)
        safe_description = self._escape_markdown_v2(description)
        safe_evidence = self._escape_markdown_v2(evidence)
        safe_recommendation = self._escape_markdown_v2(recommendation)
        safe_timestamp = self._escape_markdown_v2(timestamp.replace("T", " ").split(".")[0])
        
        lines = [
            f"{emoji} *{severity}: {safe_title}*",
            f"",
            f"📍 *Component:* {safe_component}",
            f"🕐 *Time:* {safe_timestamp}",
            f"",
            f"📝 *Description:* {safe_description}",
        ]
        
        if safe_evidence:
            lines.extend(["", f"🔍 *Evidence:* {safe_evidence}"])
        
        if safe_recommendation:
            lines.extend(["", f"💡 *Recommendation:* {safe_recommendation}"])
        
        return "\n".join(lines)
    
    def _should_alert(self, issue: Dict[str, Any]) -> bool:
        """Check if issue should trigger alert based on severity filter."""
        severity = issue.get("severity", "INFO")
        return severity in self.config.alert_severities
    
    def _get_dedup_key(self, issue: Dict[str, Any]) -> str:
        """Generate deduplication key for an issue."""
        component = issue.get("component", "UNKNOWN")
        title = issue.get("title", "Alert")
        return f"{component}:{title}"
    
    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        now = time.time()
        # Reset window if minute passed
        if now - self._sent_window_start > 60:
            self._sent_count = 0
            self._sent_window_start = now
        return self._sent_count < self.config.rate_limit_per_minute
    
    async def _send_message(self, text: str) -> bool:
        """Send message to Telegram with retries."""
        if not self.config.bot_token or not self.config.chat_id:
            self._health_status["error"] = "Missing bot_token or chat_id"
            return False
        
        url = f"{self.BASE_URL}{self.config.bot_token}/sendMessage"
        payload = {
            "chat_id": self.config.chat_id,
            "text": text,
            "parse_mode": self.config.parse_mode,
            "disable_notification": self.config.disable_notification
        }
        
        client = await self._get_client()
        
        for attempt in range(self.config.max_retries):
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                result = response.json()
                if result.get("ok"):
                    return True
                else:
                    error = result.get("description", "Unknown error")
                    self._health_status["error"] = f"Telegram API error: {error}"
            except httpx.HTTPStatusError as e:
                self._health_status["error"] = f"HTTP {e.response.status_code}: {e.response.text}"
            except httpx.RequestError as e:
                self._health_status["error"] = f"Request error: {str(e)}"
            except Exception as e:
                self._health_status["error"] = f"Unexpected error: {str(e)}"
            
            if attempt < self.config.max_retries - 1:
                await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
        
        return False
    
    async def dispatch(self, issue: Dict[str, Any], force: bool = False) -> bool:
        """
        Dispatch a single alert to Telegram.
        Returns True if sent successfully.
        """
        if not self.config.enabled:
            return False
        
        if not force and not self._should_alert(issue):
            return False
        
        # Check rate limit
        if not self._check_rate_limit():
            self._health_status["error"] = "Rate limit exceeded"
            return False
        
        # Check deduplication (5 minute window), unless forced
        if not force:
            dedup_key = self._get_dedup_key(issue)
            now = time.time()
            async with self._lock:
                if dedup_key in self._last_sent:
                    if now - self._last_sent[dedup_key] < 300:  # 5 minutes
                        return False
                self._last_sent[dedup_key] = now
        
        # Format and send
        text = self._format_alert(issue)
        success = await self._send_message(text)
        
        if success:
            self._sent_count += 1
            self._health_status["error"] = None
        
        return success
    
    async def dispatch_batch(self, issues: List[Dict[str, Any]]) -> int:
        """Dispatch multiple alerts, returns count sent."""
        sent = 0
        for issue in issues:
            if await self.dispatch(issue):
                sent += 1
            # Small delay between messages to avoid flooding
            await asyncio.sleep(0.1)
        return sent
    
    async def health_check(self) -> Dict[str, Any]:
        """Verify bot connectivity and return status."""
        if not self.config.enabled or not self.config.bot_token:
            self._health_status = {
                "ok": False,
                "last_check": datetime.now().isoformat(),
                "error": "Bot not configured"
            }
            return self._health_status
        
        url = f"{self.BASE_URL}{self.config.bot_token}/getMe"
        client = await self._get_client()
        
        try:
            response = await client.get(url, timeout=5.0)
            response.raise_for_status()
            result = response.json()
            if result.get("ok"):
                bot_info = result.get("result", {})
                self._health_status = {
                    "ok": True,
                    "last_check": datetime.now().isoformat(),
                    "error": None,
                    "bot_username": bot_info.get("username"),
                    "bot_name": bot_info.get("first_name"),
                    "can_join_groups": bot_info.get("can_join_groups"),
                    "can_read_all_group_messages": bot_info.get("can_read_all_group_messages")
                }
            else:
                self._health_status = {
                    "ok": False,
                    "last_check": datetime.now().isoformat(),
                    "error": result.get("description", "Unknown error")
                }
        except Exception as e:
            self._health_status = {
                "ok": False,
                "last_check": datetime.now().isoformat(),
                "error": str(e)
            }
        
        return self._health_status
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get cached health status (sync)."""
        return self._health_status.copy()
    
    def send_sync(self, issue: Dict[str, Any]) -> bool:
        """Synchronous wrapper for non-async contexts."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.dispatch(issue))
    
    def health_check_sync(self) -> Dict[str, Any]:
        """Synchronous health check wrapper."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.health_check())


def create_telegram_dispatcher(config: Dict[str, Any]) -> TelegramDispatcher:
    """Factory function to create TelegramDispatcher from config dict."""
    tg_config = config.get("telegram", {})
    return TelegramDispatcher(TelegramConfig(**tg_config))