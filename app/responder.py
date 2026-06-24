from __future__ import annotations

from app.models import DownloadResult, SUPPORTED_DOCUMENT_TYPES


def _counts_sentence(counts: dict[str, int]) -> str:
    parts = []
    for doc_type in SUPPORTED_DOCUMENT_TYPES:
        count = counts.get(doc_type, 0)
        if count == 0:
            parts.append(f"no {doc_type}")
        elif count == 1:
            parts.append(f"1 {doc_type}")
        else:
            parts.append(f"{count} {doc_type}")
    return ", ".join(parts[:-1]) + ", and " + parts[-1] if len(parts) > 1 else parts[0]


def build_success_reply(result: DownloadResult) -> tuple[str, str]:
    req = result.request
    meta = result.metadata
    subject = f"{req.matter_number} {req.document_type} documents"

    title = meta.title or "the requested matter"
    category_bits = " ".join(bit for bit in [meta.type_name, meta.category] if bit)
    date_bits = []
    if meta.date_received:
        date_bits.append(f"initial filing/date received: {meta.date_received}")
    if meta.date_final_submission:
        date_bits.append(f"final submission: {meta.date_final_submission}")

    lines = [
        "Hi,",
        "",
        f"{req.matter_number} is about {title}.",
    ]
    if category_bits:
        lines.append(f"It relates to {category_bits}.")
    if date_bits:
        lines.append("Key dates: " + "; ".join(date_bits) + ".")

    lines.extend(
        [
            f"I found {_counts_sentence(result.counts)}.",
            (
                f"I downloaded {len(result.downloaded_files)} out of "
                f"{result.requested_count} {req.document_type} files and attached them as a ZIP."
            ),
            "",
            "Best,",
            "Regulatory Agent",
        ]
    )

    return subject, "\n".join(lines)


def build_failure_reply(matter_number: str, document_type: str, error: str) -> tuple[str, str]:
    return (
        f"Could not complete {matter_number} {document_type} request",
        "\n".join(
            [
                "Hi,",
                "",
                f"I found your request for {document_type} from {matter_number}, but I could not complete it.",
                f"Error: {error}",
                "",
                "Best,",
                "Regulatory Agent",
            ]
        ),
    )
