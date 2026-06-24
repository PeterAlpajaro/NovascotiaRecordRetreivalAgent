from __future__ import annotations

import zipfile
from pathlib import Path


def make_zip(files: list[Path], archive_dir: str, matter_number: str, document_type: str) -> Path:
    out_dir = Path(archive_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_doc_type = document_type.lower().replace(" ", "-")
    archive_path = out_dir / f"{matter_number}-{safe_doc_type}.zip"

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            archive.write(file_path, arcname=file_path.name)

    return archive_path
