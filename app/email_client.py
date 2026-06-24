from __future__ import annotations

import email
import imaplib
import logging
import smtplib
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.utils import formataddr, parseaddr
from pathlib import Path

from bs4 import BeautifulSoup

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class IncomingEmail:
    uid: str
    subject: str
    sender: str
    reply_to: str
    message_id: str
    body: str
    raw: Message


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    return str(make_header(decode_header(value)))


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text("\n")


def _extract_body(message: Message) -> str:
    if message.is_multipart():
        plain_parts: list[str] = []
        html_parts: list[str] = []
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disposition:
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if content_type == "text/plain":
                plain_parts.append(text)
            elif content_type == "text/html":
                html_parts.append(_html_to_text(text))
        return "\n".join(plain_parts or html_parts).strip()

    payload = message.get_payload(decode=True)
    if payload is None:
        return str(message.get_payload())
    charset = message.get_content_charset() or "utf-8"
    text = payload.decode(charset, errors="replace")
    if message.get_content_type() == "text/html":
        return _html_to_text(text)
    return text.strip()


class GmailClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _connect_imap(self) -> imaplib.IMAP4_SSL:
        client = imaplib.IMAP4_SSL(self.settings.imap_host, self.settings.imap_port)
        client.login(self.settings.email_address, self.settings.email_password)
        client.select(self.settings.imap_folder)
        return client

    def fetch_unread(self) -> list[IncomingEmail]:
        with self._connect_imap() as client:
            status, data = client.uid("search", None, "UNSEEN")
            if status != "OK":
                raise RuntimeError(f"IMAP search failed: {status}")
            uids = data[0].split() if data and data[0] else []
            messages: list[IncomingEmail] = []
            for uid_bytes in uids:
                uid = uid_bytes.decode()
                status, fetched = client.uid("fetch", uid, "(BODY.PEEK[])")
                if status != "OK" or not fetched:
                    logger.warning("Failed to fetch UID %s: %s", uid, status)
                    continue
                raw_bytes = next((item[1] for item in fetched if isinstance(item, tuple)), None)
                if not raw_bytes:
                    continue
                message = email.message_from_bytes(raw_bytes)
                subject = _decode_header(message.get("Subject"))
                sender = _decode_header(message.get("From"))
                reply_to = _decode_header(message.get("Reply-To")) or sender
                message_id = message.get("Message-ID", "")
                body = _extract_body(message)
                messages.append(
                    IncomingEmail(
                        uid=uid,
                        subject=subject,
                        sender=sender,
                        reply_to=reply_to,
                        message_id=message_id,
                        body=body,
                        raw=message,
                    )
                )
            return messages

    def mark_seen(self, uid: str) -> None:
        with self._connect_imap() as client:
            status, _ = client.uid("store", uid, "+FLAGS", r"(\Seen)")
            if status != "OK":
                raise RuntimeError(f"Could not mark UID {uid} as seen: {status}")

    def send_reply(
        self,
        incoming: IncomingEmail,
        subject: str,
        body: str,
        attachment: Path | None = None,
    ) -> None:
        _, reply_addr = parseaddr(incoming.reply_to or incoming.sender)
        if not reply_addr:
            raise ValueError("No reply address found")

        message = EmailMessage()
        message["From"] = formataddr((self.settings.email_display_name, self.settings.email_address))
        message["To"] = reply_addr
        message["Subject"] = subject
        if incoming.message_id:
            message["In-Reply-To"] = incoming.message_id
            message["References"] = incoming.message_id
        message.set_content(body)

        if attachment:
            data = attachment.read_bytes()
            message.add_attachment(
                data,
                maintype="application",
                subtype="zip",
                filename=attachment.name,
            )

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=60) as smtp:
            if self.settings.smtp_use_tls:
                smtp.starttls()
            smtp.login(self.settings.email_address, self.settings.email_password)
            smtp.send_message(message)

        logger.info("Sent reply to %s with attachment=%s", reply_addr, bool(attachment))
