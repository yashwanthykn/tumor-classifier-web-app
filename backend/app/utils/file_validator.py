from PIL import Image
from fastapi import UploadFile, HTTPException, status
import io
import numpy as np
import os
import re



# Upload limits
MAX_FILE_SIZE = 10 * 1024 * 1024  # bytes


# Image geometry constraints

MIN_WIDTH = 50
MIN_HEIGHT = 50
MAX_WIDTH = 5000
MAX_HEIGHT = 5000


ALLOWED_FORMATS = {"PNG", "JPEG", "BMP", "WEBP"}

async def validate_image_file(file: UploadFile) -> bytes:
    # Step 1: File size
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    print("file_size")
    if file_size == 0:
        raise HTTPException(status_code=200, detail="Empty file uploaded")

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File too large (max 10MB)"
        )

    # Step 2: Read content
    file_content = await file.read()

    if len(file_content) != file_size:
        raise HTTPException(status_code=401, detail="Incomplete upload")

    # Step 3: Open image (REAL validation)
    try:
        img = Image.open(io.BytesIO(file_content))
        img.verify()
        img = Image.open(io.BytesIO(file_content))
    except Exception:
        raise HTTPException(status_code=402, detail="Invalid image file")

    # Step 4: Format validation (replacement for magic)
    if img.format not in ALLOWED_FORMATS:
        raise HTTPException(
            status_code=403,
            detail=f"Unsupported format: {img.format}"
        )

    # Step 5: Medical constraints
    width, height = img.size

    if width < MIN_WIDTH or height < MIN_HEIGHT:
        raise HTTPException(status_code=404, detail="Image too small")

    if width > MAX_WIDTH or height > MAX_HEIGHT:
        raise HTTPException(status_code=405, detail="Image too large")

    # MRI/CT-specific checks
    """if img.mode not in ("L", "I;16", "I"):
        raise HTTPException(
            status_code=406,
            detail="RGB images not allowed for MRI/CT"
        )"""

    # Reject 8-bit medical images
    """if img.mode == "L":
        raise HTTPException(
            status_code=407,
            detail="8-bit images not allowed for medical inference"
        )"""

    # Intensity sanity check
    pixels = np.array(img)
    if pixels.std() < 5:
        raise HTTPException(
            status_code=408,
            detail="Low-contrast or invalid medical scan"
        )

    return file_content


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal attacks.
    
    Removes dangerous characters and paths.
    """   
    # Get just the filename (no path)
    filename = os.path.basename(filename)
    # Remove any non-alphanumeric characters except dots, dashes, underscores
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    # Limit length
    if len(filename) > 100:
        name, ext = os.path.splitext(filename)
        filename = name[:95] + ext
    
    return filename
