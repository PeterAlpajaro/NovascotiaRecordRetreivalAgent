from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    email_address: str
    email_password: str
    email_display_name: str
    imap_host: str
    imap_port: int
    imap_folder: str
    smtp_host: str
    smtp_port: int
    smtp_use_tls: bool
    poll_interval_seconds: int
    max_downloads: int
    download_dir: str
    archive_dir: str
    state_path: str
    uarb_url: str
    headless: bool
    anthropic_api_key: str
    anthropic_base_url: str
    claude_model: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            email_address=os.environ["EMAIL_ADDRESS"],
            email_password=os.environ["EMAIL_PASSWORD"],
            email_display_name=os.getenv("EMAIL_DISPLAY_NAME", "Regulatory Agent"),
            imap_host=os.getenv("IMAP_HOST", "imap.gmail.com"),
            imap_port=_int("IMAP_PORT", 993),
            imap_folder=os.getenv("IMAP_FOLDER", "INBOX"),
            smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=_int("SMTP_PORT", 587),
            smtp_use_tls=_bool("SMTP_USE_TLS", True),
            poll_interval_seconds=_int("POLL_INTERVAL_SECONDS", 45),
            max_downloads=_int("MAX_DOWNLOADS", 10),
            download_dir=os.getenv("DOWNLOAD_DIR", "/app/downloads"),
            archive_dir=os.getenv("ARCHIVE_DIR", "/app/archives"),
            state_path=os.getenv("STATE_PATH", "/app/state/agent_state.json"),
            uarb_url=os.getenv("UARB_URL", "https://uarb.novascotia.ca/fmi/webd/UARB15"),
            headless=_bool("HEADLESS", True),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            anthropic_base_url=os.getenv("ANTHROPIC_BASE_URL", "http://kiro-gateway:8000"),
            claude_model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
        )
