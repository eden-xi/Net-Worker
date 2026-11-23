import os
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pymupdf
from docx import Document
from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.database.database import PROJECT_ROOT, get_connection
from backend.matching import detect_skills, split_skills

router = APIRouter()

MAX_RESUME_SIZE = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf": b"%PDF-", ".docx": b"PK"}


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
    """Store resume bytes under a random name and return (filename, path)."""
    filename = f"{uuid4().hex}{extension}"
    path = get_resume_folder() / filename
    path.write_bytes(contents)
    return filename, path


def skill_vocabulary():
    """Every skill named by any project, used to spot skills in resumes."""
    connection = get_connection()

    try:
        rows = connection.execute(
            "SELECT required_skills, nice_to_have_skills FROM projects"
        ).fetchall()
    finally:
        connection.close()

    vocabulary = []
    for row in rows:
        vocabulary.extend(split_skills(row["required_skills"]))
        vocabulary.extend(split_skills(row["nice_to_have_skills"]))

    return vocabulary


@router.post("/parse")
async def parse_resume(file: UploadFile = File(...)):
    """Read a resume and report which known skills it mentions.

    Nothing is stored; this powers the "fill skills from my resume" button.
    """
    _, _, text = await read_resume(file)

    return {
        "has_extractable_text": bool(text),
        "extracted_character_count": len(text),
        "detected_skills": detect_skills(text, skill_vocabulary()),
    }
