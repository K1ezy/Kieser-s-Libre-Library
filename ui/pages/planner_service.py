"""
Re-export shim for FlashcardService.
Preserves backward compatibility for imports from ui.pages.planner_service.
"""
from core.services.planner_service import (
    FlashcardService,
    planner_service,
)

__all__ = ["FlashcardService", "planner_service"]