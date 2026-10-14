import time
import asyncio
import re
from pathlib import Path
from typing import Tuple, Optional, Any
import logging

logger = logging.getLogger("MEDIA_HANDLER")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_UPLOADS = BASE_DIR / 'static' / 'uploads'
AVATAR_DIR = STATIC_UPLOADS / 'avatars'
COVER_DIR = STATIC_UPLOADS / 'covers'

AVATAR_DIR.mkdir(parents=True, exist_ok=True)
COVER_DIR.mkdir(parents=True, exist_ok=True)

MAX_AVATAR_SIZE = 2 * 1024 * 1024  # 2MB
MAX_COVER_SIZE = 5 * 1024 * 1024   # 5MB

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
ALLOWED_MIME_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/x-png', 'image/pjpeg'}


def validate_image(file_name: str, file_bytes: bytes, max_size: int, mime_type: Optional[str] = None) -> Tuple[bool, str, str]:
    """Validates file size, extension, and mime-type."""
    if not file_bytes:
        return False, "Uploaded file is empty.", ""

    if len(file_bytes) > max_size:
        max_mb = max_size // (1024 * 1024)
        return False, f"File exceeds maximum allowed size of {max_mb}MB.", ""

    ext = Path(file_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Unsupported file extension '{ext}'. Allowed: JPEG, PNG, WebP.", ""

    if mime_type and mime_type.lower() not in ALLOWED_MIME_TYPES:
        return False, f"Unsupported image MIME type '{mime_type}'.", ""

    return True, "", ext


def save_user_avatar(user_id: str, file_name: str, file_bytes: bytes, mime_type: Optional[str] = None) -> Tuple[bool, str]:
    """
    Saves user profile avatar to static/uploads/avatars/ with size & type validation.
    Returns (success, url_or_error_message).
    """
    valid, err, ext = validate_image(file_name, file_bytes, MAX_AVATAR_SIZE, mime_type)
    if not valid:
        return False, err

    try:
        clean_ext = ext if ext in ('.jpg', '.png', '.webp') else '.png'
        safe_uid = re.sub(r'[^a-zA-Z0-9_\-]', '', str(user_id)) or "anonymous"
        filename = f"{safe_uid}_avatar{clean_ext}"
        dest_path = AVATAR_DIR / filename
        dest_path.write_bytes(file_bytes)
        
        # Cache-busted static URL
        url = f"/static/uploads/avatars/{filename}?t={int(time.time())}"
        return True, url
    except Exception as e:
        logger.error(f"Save Avatar Error: {e}")
        return False, f"Failed to save avatar image: {str(e)}"


def save_user_cover(user_id: str, file_name: str, file_bytes: bytes, mime_type: Optional[str] = None) -> Tuple[bool, str]:
    """
    Saves user cover banner to static/uploads/covers/ with size & type validation.
    Returns (success, url_or_error_message).
    """
    valid, err, ext = validate_image(file_name, file_bytes, MAX_COVER_SIZE, mime_type)
    if not valid:
        return False, err

    try:
        clean_ext = ext if ext in ('.jpg', '.png', '.webp') else '.jpg'
        safe_uid = re.sub(r'[^a-zA-Z0-9_\-]', '', str(user_id)) or "anonymous"
        filename = f"{safe_uid}_cover{clean_ext}"
        dest_path = COVER_DIR / filename
        dest_path.write_bytes(file_bytes)
        
        # Cache-busted static URL
        url = f"/static/uploads/covers/{filename}?t={int(time.time())}"
        return True, url
    except Exception as e:
        logger.error(f"Save Cover Error: {e}")
        return False, f"Failed to save cover image: {str(e)}"


def save_user_media(user_id: str, file_bytes: bytes, file_name: str, media_type: str = "avatar") -> Tuple[bool, str, Optional[str]]:
    """
    Unified media handler dispatching to save_user_avatar or save_user_cover.
    Returns (success, message_or_error, relative_url).
    """
    if media_type == "avatar":
        success, res = save_user_avatar(user_id, file_name, file_bytes)
        return (True, "Avatar saved successfully", res) if success else (False, res, None)
    else:
        success, res = save_user_cover(user_id, file_name, file_bytes)
        return (True, "Cover saved successfully", res) if success else (False, res, None)


async def async_save_user_media(user_id: str, file_bytes: bytes, file_name: str, media_type: str = "avatar") -> Tuple[bool, str, Optional[str]]:
    """Non-blocking async variant of save_user_media executing disk I/O in thread pool."""
    return await asyncio.to_thread(save_user_media, user_id, file_bytes, file_name, media_type)


async def extract_upload_file(e: Any) -> Tuple[str, bytes]:
    """
    Robustly extracts the filename and binary byte payload from a NiceGUI UploadEventArguments object
    across both NiceGUI 1.x (content) and NiceGUI 2.x+ (file: FileUpload) APIs.
    """
    # 1. Resolve file-like or FileUpload object
    file_obj = getattr(e, 'file', None)
    if file_obj is None and hasattr(e, 'files') and e.files:
        file_obj = e.files[0]
    if file_obj is None:
        file_obj = getattr(e, 'content', None)

    # 2. Resolve filename
    file_name = getattr(e, 'name', None) or getattr(file_obj, 'name', 'uploaded_image.png')

    # 3. Read binary bytes safely
    raw_bytes = b''
    if file_obj is not None:
        if hasattr(file_obj, 'read'):
            res = file_obj.read()
            raw_bytes = await res if asyncio.iscoroutine(res) else res
        elif hasattr(file_obj, 'getvalue'):
            raw_bytes = file_obj.getvalue()
        elif isinstance(file_obj, (bytes, bytearray)):
            raw_bytes = bytes(file_obj)

    return file_name, raw_bytes


