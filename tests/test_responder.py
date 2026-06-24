from app.models import AgentRequest, DownloadResult, MatterMetadata
from app.responder import build_success_reply


def test_build_success_reply_mentions_download_count():
    result = DownloadResult(
        request=AgentRequest("M12205", "Other Documents"),
        metadata=MatterMetadata(
            matter_number="M12205",
            title="Halifax Regional Water Commission",
            type_name="Water",
            category="Capital Expenditure",
        ),
        counts={
            "Exhibits": 13,
            "Key Documents": 5,
            "Other Documents": 21,
            "Transcripts": 0,
            "Recordings": 0,
        },
        downloaded_files=[],
    )

    subject, body = build_success_reply(result)

    assert subject == "M12205 Other Documents documents"
    assert "I downloaded 0 out of 21 Other Documents files" in body
    assert "Halifax Regional Water Commission" in body
