"""PDF parser for text-first documents."""

from __future__ import annotations

import io
import os
from contextlib import redirect_stderr
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from hks.errors import ExitCode, KSError
from hks.ingest.models import ParsedDocument


def max_file_mb() -> int:
    return int(os.environ.get("HKS_MAX_FILE_MB", "200"))


def parse(path: Path) -> ParsedDocument:
    size_limit = max_file_mb() * 1024 * 1024
    if path.stat().st_size > size_limit:
        raise KSError(
            f"檔案超過大小上限：{path}",
            exit_code=ExitCode.DATAERR,
            code="OVERSIZED",
            details=[f"limit_mb={max_file_mb()}"],
        )

    try:
        with redirect_stderr(io.StringIO()):
            reader = PdfReader(str(path))
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
    except PdfReadError as exc:
        raise KSError(
            f"無法解析 PDF {path}",
            exit_code=ExitCode.DATAERR,
            code="PDF_READ_ERROR",
            details=[str(exc)],
        ) from exc
    return ParsedDocument(title=path.stem, body=text, format="pdf")
