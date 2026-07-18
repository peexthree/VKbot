import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import asyncio
from loguru import logger

def _send_email_sync(to_email: str, code: str) -> bool:
    smtp_host = os.environ.get("SMTP_HOST", "smtp.mail.ru")
    try:
        smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    except ValueError:
        smtp_port = 465
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    smtp_from = os.environ.get("SMTP_FROM", smtp_user)

    if not smtp_user or not smtp_password:
        logger.warning("SMTP credentials are not configured in .env!")
        return False

    msg = MIMEText(f"Ваш код подтверждения для приложения АНТИ-ТАР: {code}", "plain", "utf-8")
    msg["Subject"] = Header("Код подтверждения АНТИ-ТАР", "utf-8")
    msg["From"] = smtp_from
    msg["To"] = to_email

    try:
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as server:
                server.login(smtp_user, smtp_password)
                server.sendmail(smtp_from, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                if smtp_port == 587:
                    server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(smtp_from, [to_email], msg.as_string())
        logger.success(f"Verification email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False

async def send_verification_email(email: str, code: str) -> bool:
    return await asyncio.to_thread(_send_email_sync, email, code)
