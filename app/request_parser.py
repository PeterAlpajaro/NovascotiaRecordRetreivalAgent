from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

from app.config import Settings
from app.models import AgentRequest, SUPPORTED_DOCUMENT_TYPES

logger = logging.getLogger(__name__)

MATTER_RE = re.compile(r"\bM\s?(\d{5})\b", re.IGNORECASE)

DOC_TYPE_ALIASES = {
    "exhibit": "Exhibits",
    "exhibits": "Exhibits",
    "key document": "Key Documents",
    "key documents": "Key Documents",
    "key docs": "Key Documents",
    "other document": "Other Documents",
    "other documents": "Other Documents",
    "other docs": "Other Documents",
    "transcript": "Transcripts",
    "transcripts": "Transcripts",
    "recording": "Recordings",
    "recordings": "Recordings",
}


def normalize_document_type(value: str | None) -> str | None:
    if not value:
        return None
    clean = re.sub(r"\s+", " ", value.strip().lower())
    if clean in DOC_TYPE_ALIASES:
        return DOC_TYPE_ALIASES[clean]
    for supported in SUPPORTED_DOCUMENT_TYPES:
        if clean == supported.lower():
            return supported
    return None


def deterministic_parse(text: str) -> AgentRequest | None:
    matter_match = MATTER_RE.search(text)
    matter_number = f"M{matter_match.group(1)}" if matter_match else None

    lowered = re.sub(r"\s+", " ", text.lower())
    document_type = None
    for alias, canonical in sorted(DOC_TYPE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            document_type = canonical
            break

    if not matter_number or not document_type:
        return None
    return AgentRequest(matter_number=matter_number, document_type=document_type)


def _extract_json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _parse_from_llm_payload(payload: dict[str, Any]) -> AgentRequest | None:
    matter_raw = str(payload.get("matter_number") or "").upper().replace(" ", "")
    matter_match = re.fullmatch(r"M\d{5}", matter_raw)
    document_type = normalize_document_type(str(payload.get("document_type") or ""))
    if not matter_match or not document_type:
        return None
    return AgentRequest(matter_number=matter_raw, document_type=document_type)


def parse_request(text: str, settings: Settings) -> AgentRequest | None:
    """Parse a user email into a matter number and document type.

    Kiro/Anthropic is used first when configured, with a deterministic fallback
    so a gateway issue does not prevent normal challenge requests from working.
    """

    llm_request = parse_request_with_kiro(text, settings)
    if llm_request:
        return llm_request
    return deterministic_parse(text)


def parse_request_with_kiro(text: str, settings: Settings) -> AgentRequest | None:
    if not settings.anthropic_api_key:
        return None

    system = (
        "Extract a regulatory filing request from an email. Return only JSON with "
        "keys matter_number and document_type. The document_type must be exactly one "
        "of: Exhibits, Key Documents, Other Documents, Transcripts, Recordings. "
        "If either field is missing, use null for that field."
    )
    body = {
        "model": settings.claude_model,
        "max_tokens": 300,
        "temperature": 0,
        "system": system,
        "messages": [{"role": "user", "content": text[:6000]}],
    }
    url = settings.anthropic_base_url.rstrip("/") + "/v1/messages"
    headers = {
        "content-type": "application/json",
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
    }

    try:
        response = requests.post(url, headers=headers, json=body, timeout=30)
        response.raise_for_status()
        data = response.json()
        text_blocks = [
            block.get("text", "")
            for block in data.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        payload = _extract_json("\n".join(text_blocks))
        if not payload:
            return None
        parsed = _parse_from_llm_payload(payload)
        if parsed:
            logger.info("Parsed request with Kiro gateway: %s %s", parsed.matter_number, parsed.document_type)
        return parsed
    except Exception as exc:
        logger.warning("Kiro parse failed; falling back to deterministic parser: %s", exc)
        return None
