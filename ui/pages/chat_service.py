"""
Re-export shim for ChatService.
Preserves backward compatibility for imports from ui.pages.chat_service.
"""
from core.services.chat_service import *
from core.services.chat_service import (
    ChatService,
    chat_service,
    STYLE_PROMPTS,
    STARTER_PROMPTS_BOOK,
    STARTER_PROMPTS_LIBRARY,
    IDENTITY_KEYWORDS,
    GREETING_KEYWORDS,
    group_sessions_chronologically,
)
