"""
Resume files: check them, read their text, store them, find them again.

This used to be written twice (once per upload endpoint). Now there is one
read_valid_resume(), used by the apply flow.
"""

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import fitz                      # PyMuPDF: reads PDF text
from docx import Document        # python-docx: reads Word text

from backend.core import config
from backend.core.errors import Invalid, TooLarge

ALLOWED_EXTENSIONS = (".pdf", ".docx")

# Stored names are always 32 hex characters + .pdf/.docx. Checking this pattern before
# opening a file means a database value can never point outside the resume folder.
STORED_NAME = re.compile(r"^[0-9a-f]{32}\.(pdf|docx)$")


@dataclass
class ResumeFile:
    extension: str        # ".pdf" or ".docx"
    content: bytes
    text: str             # the words inside, for search and skill matching


def extract_pdf_text(content):
    with fitz.open(stream=content, filetype="pdf") as pdf:
        return "\n".join(page.get_text() for page in pdf).strip()


def extract_docx_text(content):
    document = Document(BytesIO(content))
    lines = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]

    for table in document.tables:
        for row in table.rows:
            lines.extend(cell.text for cell in row.cells if cell.text.strip())

    return "\n".join(lines)


def read_valid_resume(filename, content):
    """Check an uploaded resume and read its text. Raises Invalid / TooLarge."""
    extension = Path(filename or "").suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise Invalid("Only PDF and DOCX resumes are accepted.")

    if not content:
        raise Invalid("The uploaded resume is empty.")

    if len(content) > config.MAX_RESUME_BYTES:
        raise TooLarge("Resume must be 5 MB or smaller.")

    # The first bytes of a file tell us what it really is, whatever its name says.
    if extension == ".pdf" and not content.startswith(b"%PDF-"):
        raise Invalid("The uploaded file is not a valid PDF.")

    if extension == ".docx" and not content.startswith(b"PK"):
        raise Invalid("The uploaded file is not a valid DOCX document.")

    try:
        text = extract_pdf_text(content) if extension == ".pdf" else extract_docx_text(content)
    except Exception:
        raise Invalid("Net-Worker could not read this resume.")

    return ResumeFile(extension=extension, content=content, text=text)


def save(resume):
    """Write the file into the resume folder under a random name. Returns that name."""
    stored_name = f"{uuid4().hex}{resume.extension}"
    (config.RESUME_DIR / stored_name).write_bytes(resume.content)
    return stored_name


def delete(stored_name):
    path = path_for(stored_name)
    if path and path.exists():
        path.unlink()


def path_for(stored_name):
    """The file's full path, or None if the name is not one we created."""
    if not STORED_NAME.match(stored_name or ""):
        return None
    return config.RESUME_DIR / stored_name


def attachment_type(stored_name):
    """'pdf', 'docx', or '' when there is no usable file."""
    return Path(stored_name).suffix.lstrip(".") if path_for(stored_name) else ""
