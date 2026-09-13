import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from nicegui import app
from core.config import settings

SECRET_KEY = getattr(settings, "JWT_SECRET", settings.SECRET_KEY)
ALGORITHM = getattr(settings, "JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generates a signed JWT access token with expiration."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and validates a JWT token. Returns payload dict or None if invalid/expired."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

def is_user_authenticated() -> bool:
    """
    Checks if the current session has a valid, unexpired token.
    Automatically cleans up expired tokens if encountered.
    """
    token = app.storage.user.get('token')
    if not token:
        return False
    payload = verify_token(token)
    if not payload:
        # Stale or invalid token - clear session auth keys
        clear_user_session()
        return False
    return True

def set_user_session(user: dict, token: str):
    """
    Sets user authentication details in app.storage.user.
    Preserves theme and client preferences.
    """
    app.storage.user.update({
        'token': token,
        'user_id': user.get('id'),
        'role': user.get('role', 'user'),
        'username': user.get('username', '')
    })

def clear_user_session():
    """
    Safely clears authentication credentials from user storage while preserving
    UI preferences like 'dark_mode'.
    """
    for key in ['token', 'user_id', 'role', 'username']:
        app.storage.user.pop(key, None)

def get_current_user_info() -> Dict[str, Any]:
    """Returns basic auth info for the currently logged in user."""
    return {
        'user_id': app.storage.user.get('user_id'),
        'username': app.storage.user.get('username'),
        'role': app.storage.user.get('role', 'user'),
        'is_admin': app.storage.user.get('role') == 'admin'
    }