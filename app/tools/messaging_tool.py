from __future__ import annotations

import json
import time
from typing import Any

from app.tools.base import Tool, ToolMetadata, ToolParameter, ToolResult, ToolStatus


class MessagingTool(Tool):
    """Send messages to Slack, Discord, and Telegram.

    Parameters:
      - action (required): Operation (send)
      - platform (required): Target platform (slack, discord, telegram)
      - message (required): Message content
      - webhook_url: Webhook URL (for Slack, Discord)
      - bot_token: Bot token (for Telegram)
      - chat_id: Chat ID (for Telegram)
      - channel: Channel/room (for Slack)
      - username: Display username (optional)
      - avatar_url: Avatar URL (for Slack)
      - timeout: Max execution time in seconds (default 30)

    Security: Tokens are never logged. Requires 'tools.messaging.send' permission.
    """

    def __init__(self) -> None:
        metadata = ToolMetadata(
            name="messaging_tool",
            version="1.0.0",
            description="Send messages to Slack, Discord, Telegram",
            tool_type="builtin",
            status=ToolStatus.ACTIVE,
            parameters=[
                ToolParameter(name="action", description="Operation: send", type="string", required=True),
                ToolParameter(name="platform", description="Target platform (slack, discord, telegram)", type="string", required=True),
                ToolParameter(name="message", description="Message content", type="string", required=True),
                ToolParameter(name="webhook_url", description="Webhook URL (Slack, Discord)", type="string", required=False),
                ToolParameter(name="bot_token", description="Bot token (Telegram)", type="string", required=False),
                ToolParameter(name="chat_id", description="Chat ID (Telegram)", type="string", required=False),
                ToolParameter(name="channel", description="Channel name (Slack)", type="string", required=False),
                ToolParameter(name="username", description="Display username", type="string", required=False),
                ToolParameter(name="avatar_url", description="Avatar URL", type="string", required=False),
                ToolParameter(name="timeout", description="Max execution time in seconds", type="number", required=False, default=30.0),
            ],
            permissions_required=["tools.messaging.send"],
            capabilities=["messaging", "notifications"],
            owner="system",
            tags=["messaging", "slack", "discord", "telegram", "notifications"],
        )
        super().__init__(metadata)

    def execute(self, params: dict[str, Any]) -> ToolResult:
        errors = self.validate_params(params)
        if errors:
            return ToolResult(success=False, error_message="; ".join(errors))

        action = params["action"]
        platform = params["platform"].lower()
        message = params["message"]
        webhook_url = params.get("webhook_url", "")
        bot_token = params.get("bot_token", "")
        chat_id = params.get("chat_id", "")
        channel = params.get("channel", "")
        username = params.get("username", "JARVIS OS")
        avatar_url = params.get("avatar_url", "")
        timeout = float(params.get("timeout", 30.0))
        start = time.time()

        try:
            if action == "send":
                if platform == "slack":
                    if not webhook_url:
                        return ToolResult(success=False, error_message="webhook_url required for Slack", execution_time=time.time() - start)

                    import requests as req
                    payload: dict[str, Any] = {"text": message}
                    if username:
                        payload["username"] = username
                    if avatar_url:
                        payload["icon_url"] = avatar_url
                    if channel:
                        payload["channel"] = channel

                    resp = req.post(webhook_url, json=payload, timeout=timeout)
                    elapsed = time.time() - start
                    if resp.status_code == 200:
                        return ToolResult(success=True, output={"platform": "slack", "status_code": resp.status_code}, execution_time=elapsed)
                    return ToolResult(success=False, error_message=f"Slack API error: HTTP {resp.status_code}", execution_time=elapsed)

                elif platform == "discord":
                    if not webhook_url:
                        return ToolResult(success=False, error_message="webhook_url required for Discord", execution_time=time.time() - start)

                    import requests as req
                    payload: dict[str, Any] = {"content": message}
                    if username:
                        payload["username"] = username
                    if avatar_url:
                        payload["avatar_url"] = avatar_url

                    resp = req.post(webhook_url, json=payload, timeout=timeout)
                    elapsed = time.time() - start
                    if resp.status_code in (200, 204):
                        return ToolResult(success=True, output={"platform": "discord", "status_code": resp.status_code}, execution_time=elapsed)
                    return ToolResult(success=False, error_message=f"Discord API error: HTTP {resp.status_code}", execution_time=elapsed)

                elif platform == "telegram":
                    if not bot_token or not chat_id:
                        return ToolResult(success=False, error_message="bot_token and chat_id required for Telegram", execution_time=time.time() - start)

                    import requests as req
                    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                    payload: dict[str, Any] = {"chat_id": chat_id, "text": message}
                    if username:
                        payload["parse_mode"] = "Markdown"

                    resp = req.post(url, json=payload, timeout=timeout)
                    elapsed = time.time() - start
                    if resp.status_code == 200:
                        return ToolResult(success=True, output={"platform": "telegram", "status_code": resp.status_code}, execution_time=elapsed)
                    return ToolResult(success=False, error_message=f"Telegram API error: HTTP {resp.status_code}", execution_time=elapsed)

                else:
                    return ToolResult(success=False, error_message=f"Unsupported platform: '{platform}'. Supported: slack, discord, telegram", execution_time=time.time() - start)

            else:
                return ToolResult(success=False, error_message=f"Unknown action: '{action}'", execution_time=time.time() - start)

        except ImportError:
            return ToolResult(success=False, error_message="requests library not available", execution_time=time.time() - start)
        except Exception as e:
            return ToolResult(success=False, error_message=str(e), execution_time=time.time() - start)
