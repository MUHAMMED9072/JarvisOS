from __future__ import annotations

import json
import smtplib
import time
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolMetadata, ToolParameter, ToolResult, ToolStatus


class EmailTool(Tool):
    """Send and receive emails with attachment support.

    Parameters:
      - action (required): Operation (send, read)
      - smtp_server (required): SMTP server hostname
      - smtp_port: SMTP server port (default: 587 for TLS, 465 for SSL)
      - use_tls: Use STARTTLS (default: True)
      - username: SMTP username
      - password: SMTP password
      - from_addr (required): Sender email address
      - to_addrs (required): Recipient email address(es), comma-separated
      - subject: Email subject
      - body: Email body text
      - body_type: Body format (plain, html) (default: plain)
      - attachments: List of file paths to attach
      - cc_addrs: CC recipients, comma-separated
      - bcc_addrs: BCC recipients, comma-separated
      - timeout: Max execution time in seconds (default 30)

    Security: Passwords are never logged. Requires 'tools.email.send' permission.
    """

    def __init__(self) -> None:
        metadata = ToolMetadata(
            name="email_tool",
            version="1.0.0",
            description="Send and receive emails with attachment support",
            tool_type="builtin",
            status=ToolStatus.ACTIVE,
            parameters=[
                ToolParameter(name="action", description="Operation: send, read", type="string", required=True),
                ToolParameter(name="smtp_server", description="SMTP server hostname", type="string", required=True),
                ToolParameter(name="smtp_port", description="SMTP server port", type="number", required=False, default=587),
                ToolParameter(name="use_tls", description="Use STARTTLS", type="boolean", required=False, default=True),
                ToolParameter(name="username", description="SMTP username", type="string", required=False),
                ToolParameter(name="password", description="SMTP password", type="string", required=False),
                ToolParameter(name="from_addr", description="Sender email address", type="string", required=True),
                ToolParameter(name="to_addrs", description="Recipient email address(es), comma-separated", type="string", required=True),
                ToolParameter(name="subject", description="Email subject", type="string", required=False, default=""),
                ToolParameter(name="body", description="Email body text", type="string", required=False, default=""),
                ToolParameter(name="body_type", description="Body format (plain, html)", type="string", required=False, default="plain"),
                ToolParameter(name="attachments", description="List of file paths to attach", type="array", required=False),
                ToolParameter(name="cc_addrs", description="CC recipients, comma-separated", type="string", required=False),
                ToolParameter(name="bcc_addrs", description="BCC recipients, comma-separated", type="string", required=False),
                ToolParameter(name="timeout", description="Max execution time in seconds", type="number", required=False, default=30.0),
            ],
            permissions_required=["tools.email.send"],
            capabilities=["email_operations", "email_send"],
            owner="system",
            tags=["email", "smtp", "communication"],
        )
        super().__init__(metadata)

    def execute(self, params: dict[str, Any]) -> ToolResult:
        errors = self.validate_params(params)
        if errors:
            return ToolResult(success=False, error_message="; ".join(errors))

        action = params["action"]
        start = time.time()

        try:
            if action == "send":
                smtp_server = params["smtp_server"]
                smtp_port = int(params.get("smtp_port", 587))
                use_tls = bool(params.get("use_tls", True))
                username = params.get("username", "")
                password = params.get("password", "")
                from_addr = params["from_addr"]
                to_addrs = [a.strip() for a in params["to_addrs"].split(",") if a.strip()]
                subject = params.get("subject", "")
                body = params.get("body", "")
                body_type = params.get("body_type", "plain")
                attachment_paths = params.get("attachments", []) or []
                cc_addrs_str = params.get("cc_addrs", "")
                cc_addrs = [a.strip() for a in cc_addrs_str.split(",") if a.strip()] if cc_addrs_str else []
                bcc_addrs_str = params.get("bcc_addrs", "")
                bcc_addrs = [a.strip() for a in bcc_addrs_str.split(",") if a.strip()] if bcc_addrs_str else []

                msg = MIMEMultipart()
                msg["From"] = from_addr
                msg["To"] = ", ".join(to_addrs)
                msg["Subject"] = subject
                if cc_addrs:
                    msg["Cc"] = ", ".join(cc_addrs)

                body_part = MIMEText(body, body_type if body_type in ("plain", "html") else "plain")
                msg.attach(body_part)

                for apath in attachment_paths:
                    p = Path(apath)
                    if p.exists() and p.is_file():
                        with open(p, "rb") as f:
                            attachment = MIMEApplication(f.read(), Name=p.name)
                            attachment["Content-Disposition"] = f'attachment; filename="{p.name}"'
                            msg.attach(attachment)

                all_recipients = to_addrs + cc_addrs + bcc_addrs

                if use_tls:
                    server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
                    server.starttls()
                else:
                    server = smtplib.SMTP_SSL(smtp_server, smtp_port) if smtp_port == 465 else smtplib.SMTP(smtp_server, smtp_port, timeout=30)

                if username and password:
                    server.login(username, password)

                server.sendmail(from_addr, all_recipients, msg.as_string())
                server.quit()

                elapsed = time.time() - start
                return ToolResult(
                    success=True,
                    output={"from": from_addr, "to": to_addrs, "subject": subject, "recipients": len(all_recipients)},
                    execution_time=elapsed,
                )

            elif action == "read":
                imap_server = params.get("smtp_server", "")
                return ToolResult(
                    success=False,
                    error_message="Email read via IMAP not yet implemented. Use send action.",
                    execution_time=time.time() - start,
                )

            else:
                return ToolResult(success=False, error_message=f"Unknown action: '{action}'", execution_time=time.time() - start)

        except smtplib.SMTPAuthenticationError:
            return ToolResult(success=False, error_message="SMTP authentication failed", execution_time=time.time() - start)
        except smtplib.SMTPException as e:
            return ToolResult(success=False, error_message=f"SMTP error: {e}", execution_time=time.time() - start)
        except Exception as e:
            return ToolResult(success=False, error_message=str(e), execution_time=time.time() - start)
