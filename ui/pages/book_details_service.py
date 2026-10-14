"""
Re-export shim for BookDetailsService.
Preserves backward compatibility for imports from ui.pages.book_details_service.
"""
from core.services.book_details_service import (
    BookDetailsService,
    book_details_service,
)

__all__ = ["BookDetailsService", "book_details_service"]
