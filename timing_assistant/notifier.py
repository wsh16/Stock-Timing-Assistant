from __future__ import annotations

from dataclasses import dataclass

import requests


@dataclass(slots=True)
class NotificationResult:
    success: bool
    error: str = ""


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str) -> None:
        self.token = (token or "").strip()
        self.chat_id = (chat_id or "").strip()

    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send_message(self, text: str) -> NotificationResult:
        if not self.is_configured():
            return NotificationResult(False, "Telegram 机器人 Token 或 chat_id 未配置")

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            response = requests.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok"):
                return NotificationResult(False, str(payload))
            return NotificationResult(True, "")
        except Exception as exc:  # noqa: BLE001
            return NotificationResult(False, str(exc))
