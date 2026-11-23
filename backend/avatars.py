"""Profile pictures.

Uploads are decoded and re-encoded as a 256x256 WebP, so only real images
are stored and any embedded metadata (such as GPS location) is dropped.
"""

import os
import re
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from backend.database.database import PROJECT_ROOT

MAX_AVATAR_UPLOAD = 5 * 1024 * 1024
AVATAR_SIZE = 256
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}

# Refuse images that decompress to more than ~40 megapixels.
Image.MAX_IMAGE_PIXELS = 40_000_000

STORED_NAME = re.compile(r"^[0-9a-f]{32}\.webp$")


def get_avatar_folder():
    folder = Path(os.environ.get("NETWORKER_AVATAR_DIR", PROJECT_ROOT / "uploads" / "avatars"))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


async def process_avatar(upload: UploadFile):
    """Validate an uploaded image and return it as square WebP bytes."""
    contents = await upload.read(MAX_AVATAR_UPLOAD + 1)

    if not contents:
        raise HTTPException(400, "The uploaded image is empty.")

    if len(contents) > MAX_AVATAR_UPLOAD:
        raise HTTPException(413, "Profile pictures must be 5 MB or smaller.")

    try:
        with Image.open(BytesIO(contents)) as image:
            if image.format not in ALLOWED_FORMATS:
                raise HTTPException(400, "Use a JPG, PNG, WebP or GIF image.")

            image.seek(0)
            image = ImageOps.exif_transpose(image).convert("RGB")
            image = ImageOps.fit(image, (AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)

            output = BytesIO()
            image.save(output, "WEBP", quality=85)
            return output.getvalue()

    except HTTPException:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        raise HTTPException(400, "That file isn't an image we can read.")


def save_avatar(data):
    filename = f"{uuid4().hex}.webp"
    (get_avatar_folder() / filename).write_bytes(data)
    return filename


def avatar_path(filename):
    if not filename or not STORED_NAME.match(filename):
        return None

    path = get_avatar_folder() / filename
    return path if path.is_file() else None


def delete_avatar(filename):
    path = avatar_path(filename)
    if path:
        path.unlink(missing_ok=True)
