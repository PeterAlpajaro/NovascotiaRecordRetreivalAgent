from app.request_parser import deterministic_parse, normalize_document_type


def test_deterministic_parse_matter_and_other_documents():
    parsed = deterministic_parse("Can you give me Other Documents files from M12205?")

    assert parsed is not None
    assert parsed.matter_number == "M12205"
    assert parsed.document_type == "Other Documents"


def test_deterministic_parse_normalizes_spaced_matter_number():
    parsed = deterministic_parse("Please send exhibits for M 12383")

    assert parsed is not None
    assert parsed.matter_number == "M12383"
    assert parsed.document_type == "Exhibits"


def test_normalize_document_type_aliases():
    assert normalize_document_type("key docs") == "Key Documents"
    assert normalize_document_type("recording") == "Recordings"
    assert normalize_document_type("not a real tab") is None
