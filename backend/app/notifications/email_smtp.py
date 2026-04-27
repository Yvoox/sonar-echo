"""SMTP channel — works against MailHog in dev, real SMTP in prod."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.config import settings
from app.notifications.channel import register


class SmtpChannel:
    type = "email"

    async def deliver(self, *, subject: str, body: str, config: dict) -> None:
        to = config.get("to")
        if not to:
            raise ValueError("email channel requires config.to")
        msg = EmailMessage()
        msg["From"] = config.get("from") or settings.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)

        if settings.smtp_tls:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
                s.starttls()
                if settings.smtp_user and settings.smtp_password:
                    s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
                if settings.smtp_user and settings.smtp_password:
                    s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)


# auto-register at import
register(SmtpChannel())
