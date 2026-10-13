import time
from pathlib import Path
from typing import Tuple, Optional
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
        filename = f"{user_id}_avatar{clean_ext}"
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
        filename = f"{user_id}_cover{clean_ext}"
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

