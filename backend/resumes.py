"""Resume upload validation, text extraction and storage."""

import os
import re
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pymupdf
from docx import Document
from fastapi import HTTPException, UploadFile

from backend.database.database import PROJECT_ROOT

MAX_RESUME_SIZE = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf": b"%PDF-", ".docx": b"PK"}

# Stored names are always <32 hex chars>.<ext>; anything else is rejected
# before it gets near the filesystem.
STORED_NAME = re.compile(r"^[0-9a-f]{32}\.(pdf|docx)$")

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def get_resume_folder():
    folder = Path(
        os.environ.get("NETWORKER_UPLOAD_DIR", PROJECT_ROOT / "uploads" / "resumes")
    )
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def extract_pdf_text(file_contents):
    with pymupdf.open(stream=file_contents, filetype="pdf") as pdf:
        return "\n".join(page.get_text() for page in pdf).strip()


def extract_docx_text(file_contents):
    document = Document(BytesIO(file_contents))

    lines = [p.text for p in document.paragraphs if p.text.strip()]

    for table in document.tables:
        for row in table.rows:
            lines.extend(cell.text for cell in row.cells if cell.text.strip())

    return "\n".join(lines)


async def read_resume(upload: UploadFile):
    """Validate an uploaded resume and extract its text.

    Returns (file_bytes, extension, text). Raises HTTPException on bad input.
    """
    extension = Path(upload.filename or "").suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Only PDF and DOCX resumes are accepted.")

    contents = await upload.read(MAX_RESUME_SIZE + 1)

    if not contents:
        raise HTTPException(400, "The uploaded resume is empty.")

    if len(contents) > MAX_RESUME_SIZE:
        raise HTTPException(413, "Resume must be 5 MB or smaller.")

    if not contents.startswith(ALLOWED_EXTENSIONS[extension]):
        raise HTTPException(
            400, f"The uploaded file is not a valid {extension[1:].upper()} file."
        )

    try:
        if extension == ".pdf":
            text = extract_pdf_text(contents)
        else:
            text = extract_docx_text(contents)
    except Exception:
        raise HTTPException(400, "ProjectHub could not read this resume.")

    return contents, extension, text


def save_resume(contents, extension):
    """Store resume bytes under a random name and return the name."""
    filename = f"{uuid4().hex}{extension}"
    (get_resume_folder() / filename).write_bytes(contents)
    return filename


def resume_path(filename):
    """Path of a stored resume, or None if the name is invalid or missing."""
    if not filename or not STORED_NAME.match(filename):
        return None

    path = get_resume_folder() / filename
    return path if path.is_file() else None


def delete_resume_if_unused(connection, filename):
    """Remove a replaced resume unless an application still refers to it."""
    path = resume_path(filename)

    if path is None:
        return

    in_use = connection.execute(
        "SELECT 1 FROM applications WHERE resume_filename = ? LIMIT 1", (filename,)
    ).fetchone()

    if not in_use:
        path.unlink(missing_ok=True)
