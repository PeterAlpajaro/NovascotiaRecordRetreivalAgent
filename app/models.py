from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


SUPPORTED_DOCUMENT_TYPES = (
    "Exhibits",
    "Key Documents",
    "Other Documents",
    "Transcripts",
    "Recordings",
)


@dataclass(frozen=True)
class AgentRequest:
    matter_number: str
    document_type: str


@dataclass
class MatterMetadata:
    matter_number: str
    title: str = ""
    status: str = ""
    type_name: str = ""
    category: str = ""
    date_received: str = ""
    date_final_submission: str = ""


@dataclass
class DownloadResult:
    request: AgentRequest
    metadata: MatterMetadata
    counts: dict[str, int] = field(default_factory=dict)
    downloaded_files: list[Path] = field(default_factory=list)
    archive_path: Path | None = None

    @property
    def requested_count(self) -> int:
        return self.counts.get(self.request.document_type, 0)
