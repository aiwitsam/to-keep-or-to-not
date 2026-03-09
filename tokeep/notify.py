"""Notifications after backup completion."""

import subprocess
import smtplib
from email.mime.text import MIMEText
from dataclasses import dataclass
from typing import Optional


@dataclass
class NotifyConfig:
    """Notification configuration."""
    enabled: bool = False
    desktop: bool = True
    email: Optional[str] = None
    smtp_host: str = "localhost"
    smtp_port: int = 25
    smtp_from: str = "tokeep@localhost"


def load_notify_config(config: dict) -> NotifyConfig:
    """Extract notification settings from config dict."""
    notify = config.get("notifications", {})
    return NotifyConfig(
        enabled=notify.get("enabled", False),
        desktop=notify.get("desktop", True),
        email=notify.get("email"),
        smtp_host=notify.get("smtp_host", "localhost"),
        smtp_port=notify.get("smtp_port", 25),
        smtp_from=notify.get("smtp_from", "tokeep@localhost"),
    )


def _desktop_notify(title: str, body: str) -> bool:
    """Send a desktop notification via notify-send (Linux)."""
    try:
        result = subprocess.run(
            ["notify-send", "--app-name=tokeep", title, body],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _email_notify(notify_config: NotifyConfig, subject: str, body: str) -> bool:
    """Send an email notification via SMTP."""
    if not notify_config.email:
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = notify_config.smtp_from
    msg["To"] = notify_config.email

    try:
        with smtplib.SMTP(notify_config.smtp_host, notify_config.smtp_port, timeout=10) as server:
            server.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError):
        return False


def _format_backup_summary(result) -> tuple[str, str]:
    """Format a backup result into notification title and body."""
    if result.success:
        title = f"tokeep: Backup complete ({result.projects_synced} projects)"
        status = "SUCCESS"
    else:
        title = f"tokeep: Backup failed ({result.projects_failed} errors)"
        status = "FAILED"

    lines = [
        f"Status: {status}",
        f"Projects synced: {result.projects_synced}",
    ]

    if result.projects_failed:
        lines.append(f"Projects failed: {result.projects_failed}")

    if result.duration_seconds:
        if result.duration_seconds < 60:
            lines.append(f"Duration: {result.duration_seconds:.1f}s")
        else:
            mins = int(result.duration_seconds // 60)
            secs = result.duration_seconds % 60
            lines.append(f"Duration: {mins}m {secs:.0f}s")

    if result.errors:
        lines.append("")
        lines.append("Errors:")
        for err in result.errors[:5]:
            lines.append(f"  - {err}")

    return title, "\n".join(lines)


def send_backup_notification(config: dict, result) -> dict[str, bool]:
    """Send notifications for a backup result.

    Args:
        config: Full app config dict
        result: BackupResult object

    Returns:
        Dict of {method: success} for each attempted notification
    """
    notify_config = load_notify_config(config)
    if not notify_config.enabled:
        return {}

    title, body = _format_backup_summary(result)
    results = {}

    if notify_config.desktop:
        results["desktop"] = _desktop_notify(title, body)

    if notify_config.email:
        results["email"] = _email_notify(notify_config, f"[tokeep] {title}", body)

    return results
