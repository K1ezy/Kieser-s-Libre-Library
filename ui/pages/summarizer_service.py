"""
Summarizer Service for TARS AI.
Handles document path resolution, multi-stage text extraction, chunk partitioning,
study prompt engineering, and LLM streaming for book summarization.
Decouples AI domain logic from NiceGUI interface code.
"""

from pathlib import Path
from typing import Optional, Dict, Any, AsyncGenerator, List
import logging
from nicegui import run

from core.database.mongo_manager import mongo_db
from core.ai_engine.llm_engine import tars_engine
from core.utils.text_extractor import extract_text_from_file

logger = logging.getLogger("SUMMARIZER_SERVICE")

SUMMARY_MODES = {
    'detailed': 'Exhaustive Study Guide (Full Depth)',
    'brief': 'Executive Overview (Concise)',
    'concepts': 'Key Concepts & Definitions',
    'qa': 'Q&A Active Recall Prep'
}

MAX_SINGLE_PASS_CHARS = 10000
CHUNK_SAMPLE_SIZE = 1600


class SummarizerService:
    """Domain service for extracting, structuring, and generating AI document summaries."""

    @staticmethod
    def partition_document_text(raw_text: str) -> str:
        """
        Intelligently samples and partitions long documents across 5 key structural sections:
        Part 1: Introduction & Beginning
        Part 2: Early Sections
        Part 3: Core Middle Sections
        Part 4: Advanced / Later Topics
        Part 5: Conclusion & Takeaways
        """
        clean_text = raw_text.strip()
        if len(clean_text) <= MAX_SINGLE_PASS_CHARS:
            return clean_text

        chunk = CHUNK_SAMPLE_SIZE
        total = len(clean_text)
        p1 = clean_text[:chunk]
        p2 = clean_text[total // 4 : total // 4 + chunk]
        p3 = clean_text[total // 2 : total // 2 + chunk]
        p4 = clean_text[3 * total // 4 : 3 * total // 4 + chunk]
        p5 = clean_text[-chunk:]

        return (
            f"=== PART 1: INTRODUCTION & BEGINNING ===\n{p1}\n\n"
            f"=== PART 2: EARLY SECTIONS ===\n{p2}\n\n"
            f"=== PART 3: CORE MIDDLE SECTIONS ===\n{p3}\n\n"
            f"=== PART 4: ADVANCED / LATER TOPICS ===\n{p4}\n\n"
            f"=== PART 5: CONCLUSION & TAKEAWAYS ===\n{p5}"
        )

    @staticmethod
    def build_summary_messages(mode: str, title: str, context_text: str) -> List[Dict[str, str]]:
        """Constructs system and user prompt payloads based on the selected study mode."""
        if mode == 'brief':
            prompt_text = (
                f"You are an expert research librarian and academic analyst.\n"
                f"Below is the verified text extracted from the document: '{title}'.\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Base your summary STRICTLY and EXCLUSIVELY on the provided text below. Do NOT hallucinate outside materials.\n"
                "2. Provide an authoritative Executive Overview highlighting the central thesis, primary objectives, key findings, and strategic takeaways.\n"
                "3. Structure your response clearly using markdown headings:\n"
                "### 🎯 Executive Summary & Core Objective\n"
                "### 🔍 Key Findings & Main Themes\n"
                "### 💡 Major Takeaways & Practical Applications\n\n"
                f"--- START OF DOCUMENT: {title} ---\n{context_text}\n--- END OF DOCUMENT ---"
            )
        elif mode == 'concepts':
            prompt_text = (
                f"You are a master educator and subject matter expert.\n"
                f"Below is the verified text extracted from the document: '{title}'.\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Extract and explain all CORE CONCEPTS, TERMINOLOGY, FRAMEWORKS, and PRINCIPLES found in this document.\n"
                "2. Base explanations purely on the text provided.\n"
                "3. Structure your response under:\n"
                "### 📚 Foundational Terminology & Definitions\n"
                "### ⚙️ Core Principles, Frameworks & Methodologies\n"
                "### ⚠️ Critical Distinctions & Rules to Remember\n\n"
                f"--- START OF DOCUMENT: {title} ---\n{context_text}\n--- END OF DOCUMENT ---"
            )
        elif mode == 'qa':
            prompt_text = (
                f"You are a university professor creating an active recall exam review guide.\n"
                f"Below is the verified text extracted from the document: '{title}'.\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Generate 8-12 high-yield study questions and in-depth answers covering the most vital topics of this document.\n"
                "2. Include both conceptual understanding and applied analysis questions.\n"
                "3. Format each item clearly with:\n"
                "**Q[N]: [Clear, testable question]**\n"
                "**Answer:** [Accurate explanation referencing the document]\n\n"
                f"--- START OF DOCUMENT: {title} ---\n{context_text}\n--- END OF DOCUMENT ---"
            )
        else:
            prompt_text = (
                f"You are an expert academic professor and educational summarizer.\n"
                f"Below is the verified text extracted from the document: '{title}'.\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Base your summary STRICTLY and EXCLUSIVELY on the provided document text below. Do NOT invent outside topics or reference unrelated domains.\n"
                "2. BE EXHAUSTIVE AND THOROUGH: Ensure all major sections, arguments, methodologies, criteria, and classifications present in the text are comprehensively covered.\n"
                "3. Derive section headings DYNAMICALLY based directly on the actual subject matter and themes of the document.\n"
                "4. Structure your response with the following format:\n"
                "### 1. Document Overview & Primary Goals\n"
                "- Context, purpose, scope, and target audience.\n\n"
                "### 2. Comprehensive Section & Topic Breakdown\n"
                "- In-depth explanation of each key topic, model, or narrative progression presented in the text.\n\n"
                "### 3. Key Methodologies, Evidence & Analysis\n"
                "- Specific data, procedures, qualitative/quantitative points, or arguments made.\n\n"
                "### 4. Critical Insights & Key Implications\n"
                "- High-yield conclusions, lessons learned, and future directions.\n\n"
                f"--- START OF DOCUMENT: {title} ---\n{context_text}\n--- END OF DOCUMENT ---"
            )

        return [
            {"role": "system", "content": "You are a professional research librarian and educational document summarizer."},
            {"role": "user", "content": prompt_text}
        ]

    @staticmethod
    async def resolve_document_file(book_id: str, book_doc: Optional[dict] = None) -> Optional[str]:
        """Resolves the physical file path for the book via centralized repository helper."""
        if not book_doc and book_id:
            book_doc = await mongo_db.get_book_details(book_id)
        return mongo_db.resolve_document_path(book_id, book_doc)

    @staticmethod
    async def extract_book_content(file_path: str) -> Optional[str]:
        """Reads and extracts raw text from a local document file asynchronously."""
        if not file_path or not Path(file_path).exists():
            return None
        return await run.io_bound(extract_text_from_file, file_path)

    @staticmethod
    async def save_summary_to_database(book_id: str, summary_text: str) -> bool:
        """Saves generated summary to the book record in MongoDB."""
        return await mongo_db.save_book_summary(book_id, summary_text)


# Singleton instance
summarizer_service = SummarizerService()
