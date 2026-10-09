"""
Chat Service for TARS AI Librarian.
Handles business logic, intent detection, prompt engineering, RAG orchestration,
and conversation formatting, decoupling AI domain operations from NiceGUI presentation.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any
import logging
import string
import time
from nicegui import run

from core.database.mongo_manager import mongo_db
from core.ai_engine.rag_pipeline import tars_archive

logger = logging.getLogger("CHAT_SERVICE")

# ==========================================
# 📑 CONFIGURATION & PROMPT CONSTANTS
# ==========================================

STYLE_PROMPTS = {
    'Balanced': "Provide clear, structured, well-formatted answers with citations where applicable.",
    'Concise': "Provide direct, ultra-concise responses with short bullet points. Avoid filler.",
    'Academic': "Provide an in-depth academic analysis with historical/theoretical context, critical critique, and comprehensive citations.",
    'Exam Prep': "Provide high-yield study notes, key terms with definitions, potential test/exam questions, and memory mnemonics."
}

STARTER_PROMPTS_BOOK = [
    ("💡 Executive Summary", "Give me a comprehensive overview and core takeaways of this document."),
    ("🎯 Key Arguments", "What are the primary arguments, methodologies, and conclusions presented in this document?"),
    ("🧠 Active Recall Quiz", "Quiz me with 3 challenging active recall questions based on this document."),
    ("🔍 Explain Simply", "Explain the most important concepts from this document in clear, beginner-friendly terms.")
]

STARTER_PROMPTS_LIBRARY = [
    ("📚 Library Inventory", "What books and documents do I currently have indexed in my library?"),
    ("🔬 Cross-Book Synthesis", "Synthesize the central themes and connections across my indexed documents."),
    ("📖 Study Recommendations", "Based on the topics in my collection, what should I study or focus on next?"),
    ("🎓 Socratic Tutoring", "Turn on Teaching Mode and tutor me step-by-step on a core topic from my library.")
]

IDENTITY_KEYWORDS = {"who are you", "what are you", "identify", "your function", "introduce yourself"}
GREETING_KEYWORDS = {"hello", "hi", "hey", "tars", "yo", "greetings", "good morning", "good afternoon", "good evening"}


class ChatService:
    """Domain service orchestrating chat business logic, RAG retrieval, and prompt creation."""

    @staticmethod
    def should_skip_rag(text: str) -> bool:
        """Determines if query is a simple greeting or identity question where RAG should be skipped."""
        if not text:
            return True
        clean_input = text.lower().translate(str.maketrans('', '', string.punctuation)).strip()
        is_identity = any(k in clean_input for k in IDENTITY_KEYWORDS)
        is_greeting = (
            clean_input in GREETING_KEYWORDS or
            (len(clean_input.split()) <= 3 and any(g in clean_input for g in GREETING_KEYWORDS))
        )
        return is_identity or is_greeting

    @staticmethod
    def group_sessions_chronologically(sessions: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Groups sessions into temporal categories: Today, Yesterday, 7 Days, Month, Older."""
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        yesterday_start = today_start - 86400
        seven_days_start = today_start - (6 * 86400)
        thirty_days_start = today_start - (29 * 86400)

        groups: Dict[str, List[Dict[str, Any]]] = {
            'Today': [],
            'Yesterday': [],
            'Previous 7 Days': [],
            'This Month': [],
            'Older': []
        }

        for s in (sessions or []):
            ts = s.get('timestamp', 0)
            if ts >= today_start:
                groups['Today'].append(s)
            elif ts >= yesterday_start:
                groups['Yesterday'].append(s)
            elif ts >= seven_days_start:
                groups['Previous 7 Days'].append(s)
            elif ts >= thirty_days_start:
                groups['This Month'].append(s)
            else:
                try:
                    m_key = datetime.fromtimestamp(ts).strftime("%B %Y")
                except Exception:
                    m_key = "Older"
                groups.setdefault(m_key, []).append(s)

        return {k: v for k, v in groups.items() if v}

    @staticmethod
    def build_system_persona(
        chat_style: str = "Balanced",
        focus_book_title: Optional[str] = None,
        teaching_mode: bool = False,
        is_review_mode: bool = False,
        inventory: str = "",
        rag_text: str = ""
    ) -> str:
        """Constructs system prompt combining library inventory, retrieved RAG context, and persona instructions."""
        active_style_prompt = STYLE_PROMPTS.get(chat_style, STYLE_PROMPTS['Balanced'])
        persona = (
            "You are TARS, the Digital Librarian. You assist users with their personal digital library, study materials, and questions.\n"
            f"RESPONSE STYLE INSTRUCTION: {active_style_prompt}\n\n"
            "Use the provided LIBRARY INVENTORY to tell users what books they have, and the KNOWLEDGE BASE to answer questions with precision.\n"
            "Always include source and page number citations when referencing document knowledge (e.g. '[Source: title, Page X]').\n\n"
            f"1. **LIBRARY INVENTORY:**\n{inventory}\n"
            f"2. **KNOWLEDGE BASE:**\n{rag_text}\n"
        )
        if focus_book_title:
            persona += f"\nFOCUS DOCUMENT: The user is specifically asking about '{focus_book_title}'. Focus your answers on this document."
        if teaching_mode:
            persona += "\nTEACHING MODE: Socratic teaching style. Guide the user with questions rather than immediate answers."
        elif is_review_mode:
            persona += "\nCODE REVIEW MODE: Review provided code for architecture, performance, security, and cleanliness."

        return persona

    @staticmethod
    async def perform_rag_search(
        text: str,
        focus_book_id: Optional[str] = None,
        focus_book_title: Optional[str] = None
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Executes vector retrieval and formats context snippets and citations.
        Returns (rag_text, citations).
        """
        rag_text = ""
        citations: List[Dict[str, Any]] = []
        try:
            filter_source = None
            if focus_book_id:
                book_doc = await mongo_db.get_book_details(focus_book_id)
                if book_doc:
                    local_p = book_doc.get('local_path')
                    filter_source = Path(local_p).name if local_p else focus_book_id

            raw_hits = await run.io_bound(tars_archive.search_with_metadata, text, 4, filter_source, focus_book_id)
            if raw_hits:
                rag_parts = []
                for h in raw_hits:
                    src = h.get('source', 'Library Document')
                    p_val = h.get('page')
                    page_str = f" [Page {p_val}]" if p_val else ""
                    rag_parts.append(f"[Document: {src}{page_str}]\n{h.get('text', '')}")

                    cit_key = f"{src}_{p_val}"
                    if not any(c.get('key') == cit_key for c in citations):
                        citations.append({
                            "key": cit_key,
                            "source": src,
                            "title": h.get('title') or src,
                            "page": p_val,
                            "book_id": h.get('book_id')
                        })
                rag_text = "\n\n[RETRIEVED DOCUMENT CONTEXT]:\n" + "\n---\n".join(rag_parts)
        except Exception as e:
            logger.error(f"RAG Search Error: {e}")

        return rag_text, citations

    @staticmethod
    def build_messages_payload(system_persona: str, history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Constructs and validates the message payload for LLM streaming."""
        valid_history = [
            {"role": m['role'], "content": m['content']}
            for m in (history or [])
            if m and 'role' in m and 'content' in m
        ]
        return [{"role": "system", "content": system_persona}] + valid_history

    @staticmethod
    def export_chat_markdown(messages: List[Dict[str, Any]], focus_book_title: Optional[str], session_id: str) -> str:
        """Formats conversation messages into a clean Markdown document."""
        title = focus_book_title or "General Library Knowledge"
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        lines = [
            "# Conversation with TARS AI",
            f"- **Context / Focus:** {title}",
            f"- **Date:** {date_str}",
            f"- **Engine:** Local Offline RAG",
            f"- **Session ID:** `{session_id}`",
            "\n---\n"
        ]
        for m in (messages or []):
            role = "👤 User" if m.get('role') == 'user' else "🤖 TARS AI"
            lines.append(f"### {role}\n\n{m.get('content', '').strip()}\n")

        return "\n".join(lines)


# Singleton instance and module-level helper exports
chat_service = ChatService()
group_sessions_chronologically = ChatService.group_sessions_chronologically
