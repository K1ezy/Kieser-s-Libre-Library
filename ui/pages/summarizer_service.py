"""
Re-export shim for SummarizerService.
Preserves backward compatibility for imports from ui.pages.summarizer_service.
"""
from core.services.summarizer_service import *
from core.services.summarizer_service import (
    SummarizerService,
    summarizer_service,
    SUMMARY_MODES,
    MAX_SINGLE_PASS_CHARS,
    CHUNK_SAMPLE_SIZE,
)
