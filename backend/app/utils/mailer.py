"""Outbound email via SMTP.

If SMTP_HOST is not configured the message is logged instead of sent —
this keeps local development and tests working without an SMTP server.
In production, set SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD/SMTP_FROM.
"""
import logging
import smtplib
from email.message import EmailMessage

from flask import current_app

logger = logging.getLogger(__name__)


def send_email(to, subject, body, html=None):
    """Send an email (plain text, optionally with an HTML alternative).
    Returns True if sent (or logged in dev)."""
    host = current_app.config.get("SMTP_HOST")
    if not host:
        # No SMTP configured — log the message so the link is still reachable
        # in development. NEVER do this in production.
        if current_app.config.get("FLASK_ENV") == "production":
            logger.error("SMTP not configured; cannot send email to %s: %s", to, subject)
            return False
        logger.info("SMTP not configured — email to %s | %s\n%s", to, subject, body)
        return True

    msg = EmailMessage()
    msg["From"] = current_app.config.get("SMTP_FROM") or current_app.config.get("SMTP_USER")
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")

    try:
        port = int(current_app.config.get("SMTP_PORT", 587))
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls()
            user = current_app.config.get("SMTP_USER")
            password = current_app.config.get("SMTP_PASSWORD")
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False
