
from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
from io import BytesIO
from uuid import uuid4

import fitz
from docx import Document


router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESUME_FOLDER = PROJECT_ROOT / "uploads" / "resumes"
RESUME_FOLDER.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 5 * 1024 * 1024


def extract_pdf_text(file_contents):
    pdf = fitz.open(stream=file_contents, filetype="pdf")

    extracted_text = ""

    for page in pdf:
        extracted_text += page.get_text() + "\n"

    pdf.close()
    return extracted_text.strip()


def extract_docx_text(file_contents):
    document = Document(BytesIO(file_contents))

    extracted_text = []

    for paragraph in document.paragraphs:
        if paragraph.text.strip():
            extracted_text.append(paragraph.text)

    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    extracted_text.append(cell.text)

    return "\n".join(extracted_text)


@router.post("/upload")
async def upload_resume(file: UploadFile = File(...)):

    original_filename = file.filename or ""
    extension = Path(original_filename).suffix.lower()

    if extension not in [".pdf", ".docx"]:
        raise HTTPException(
            status_code=400,
            detail="Only PDF and DOCX resumes are accepted."
        )

    file_contents = await file.read(MAX_FILE_SIZE + 1)

    if not file_contents:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty."
        )

    if len(file_contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Resume must be 5 MB or smaller."
        )

    if extension == ".pdf":
        if not file_contents.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is not a valid PDF."
            )

    elif extension == ".docx":
        if not file_contents.startswith(b"PK"):
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is not a valid DOCX document."
            )

    try:
        if extension == ".pdf":
            extracted_text = extract_pdf_text(file_contents)
        else:
            extracted_text = extract_docx_text(file_contents)

    except Exception:
        raise HTTPException(
            status_code=400,
            detail="ProjectHub could not read this resume."
        )

    stored_filename = f"{uuid4().hex}{extension}"
    save_path = RESUME_FOLDER / stored_filename
    save_path.write_bytes(file_contents)

    return {
        "message": "Resume uploaded and processed successfully.",
        "stored_filename": stored_filename,
        "original_filename": Path(original_filename).name,
        "extracted_character_count": len(extracted_text),
        "has_extractable_text": bool(extracted_text)
    }
