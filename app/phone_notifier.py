"""Phone notification via ntfy.sh push notifications.

Sends alerts to a ntfy.sh topic; the ntfy app on Android displays them
as system notifications.

Also sends periodic heartbeats to a status topic so GitHub Actions can
check streak status even when the laptop is off.
"""

import json
import logging
import urllib.request

import app.config as config

logger = logging.getLogger(__name__)

_NTFY_URL = "https://ntfy.sh"


def _post(topic: str, body: bytes, content_type: str = "text/plain",
          title: str = "") -> bool:
    if not topic:
        return False
    url = f"{_NTFY_URL}/{topic}"
    headers = {"Content-Type": content_type}
    if title:
        headers["Title"] = title
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return True
            logger.warning("ntfy.sh %s returned %d", topic, resp.status)
            return False
    except Exception as exc:
        logger.warning("ntfy.sh %s error: %s", topic, exc)
        return False


class PhoneNotifier:
    """Sends push notifications via ntfy.sh."""

    @staticmethod
    def is_configured() -> bool:
        return bool(config.NTFY_TOPIC)

    @staticmethod
    def send_message(text: str) -> bool:
        if not PhoneNotifier.is_configured():
            logger.warning("PhoneNotifier not configured — no topic set")
            return False
        return _post(config.NTFY_TOPIC, text.encode("utf-8"), title="Laptop Momentum")

    @staticmethod
    def send_heartbeat(active_minutes: int, streak_safe: bool) -> bool:
        """Send periodic status heartbeat to the status topic.

        GitHub Actions fetches these to decide whether to alert.
        """
        if not config.NTFY_STATUS_TOPIC:
            return False
        data = json.dumps({
            "type": "heartbeat",
            "active_minutes": active_minutes,
            "streak_safe": streak_safe,
        }).encode("utf-8")
        return _post(config.NTFY_STATUS_TOPIC, data,
                     content_type="application/json")
