import magic
from PIL import Image
from fastapi import UploadFile, HTTPException, status
import io

# Allowed MIME types for images
ALLOWED_MIME_TYPES = [
    'image/jpeg',
    'image/jpg', 
    'image/png',
    'image/webp',
    'image/bmp'
]

# Maximum file size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes

# Minimum dimensions (prevent 1x1 pixel attacks)
MIN_WIDTH = 50
MIN_HEIGHT = 50

# Maximum dimensions (prevent memory exhaustion)
MAX_WIDTH = 5000
MAX_HEIGHT = 5000


async def validate_image_file(file: UploadFile) -> None:
    """
    Comprehensive image file validation.
    
    Checks:
    1. File size
    2. MIME type (via magic numbers)
    3. File integrity (can be opened as image)
    4. Image dimensions
    
    Raises HTTPException if validation fails.
    """
    
    # Step 1: Validate file size
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset to beginning
    
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE / (1024*1024):.1f}MB"
        )
    
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file uploaded"
        )
    
    # Step 2: Read file content for validation
    file_content = await file.read()
    await file.seek(0)  # Reset for later use
    
    # Step 3: Validate MIME type using magic numbers (not just extension)
    mime_type = magic.from_buffer(file_content, mime=True)
    
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {mime_type}. Only images are allowed (JPEG, PNG, WebP, BMP)."
        )
    
    # Step 4: Validate file can be opened as image (integrity check)
    try:
        img = Image.open(io.BytesIO(file_content))
        img.verify()  # Verify it's a valid image
        
        # Re-open for dimension check (verify() closes the image)
        img = Image.open(io.BytesIO(file_content))
        width, height = img.size
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or corrupted image file"
        )
    
    # Step 5: Validate dimensions
    if width < MIN_WIDTH or height < MIN_HEIGHT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image too small. Minimum dimensions: {MIN_WIDTH}x{MIN_HEIGHT}px"
        )
    
    if width > MAX_WIDTH or height > MAX_HEIGHT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image too large. Maximum dimensions: {MAX_WIDTH}x{MAX_HEIGHT}px"
        )
    
    # All validations passed
    return None


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal attacks.
    
    Removes dangerous characters and paths.
    """
    import os
    import re
    
    # Get just the filename (no path)
    filename = os.path.basename(filename)
    
    # Remove any non-alphanumeric characters except dots, dashes, underscores
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    
    # Limit length
    if len(filename) > 100:
        name, ext = os.path.splitext(filename)
        filename = name[:95] + ext
    
    return filename