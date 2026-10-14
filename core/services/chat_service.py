"""
Chat Service for TARS AI Librarian.
Handles business logic, intent detection, prompt engineering, RAG orchestration,
and conversation formatting, decoupling AI domain operations from NiceGUI presentation.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any, Set
import logging
import string
import re
import time
from nicegui import run

from core.database.mongo_manager import mongo_db
from core.ai_engine.rag_pipeline import tars_archive

logger = logging.getLogger("CHAT_SERVICE")

# ==========================================
# 📑 CONFIGURATION & PROMPT CONSTANTS
# ==========================================

STYLE_PROMPTS = {
    'Balanced': "Provide a thorough, well-structured, and clear answer. Use headings, bullet points, and exact page citations. Do not truncate essential concepts.",
    'Concise': "Provide a direct, high-yield summary with concise bullet points. Avoid filler while retaining core definitions.",
    'Academic': "Provide an in-depth academic lecture analysis with theoretical context, methodical critique, definitions, and comprehensive citations.",
    'Exam Prep': "Provide an exhaustive exam preparation study guide with key definitions, principles, comparison tables, test questions, and mnemonics."
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
SUMMARY_KEYWORDS = (
    "summarize", "summary", "overview", "everything", "all topics", "whole lecture",
    "whole book", "whole document", "full lecture", "full summary", "key takeaways",
    "study guide", "lecture notes", "all of it", "explain everything", "entire document",
    "breakdown", "all slides"
)
CONTINUE_KEYWORDS = (
    "continue", "more", "tell me more", "what else", "go on", "keep going", "next part", "give me more"
)


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
    def extract_catalog_search_term(text: str) -> str:
        """Extracts author or title candidates from catalog inquiries."""
        if not text:
            return ""
        cleaned = text.strip()
        patterns = [
            r'what\s+are\s+the\s+',
            r'what\s+books\s+do\s+(we|i|you)\s+have\s+(by\s+|on\s+|about\s+|in\s+)?',
            r'which\s+books\s+do\s+(we|i|you)\s+have\s+(by\s+|on\s+|about\s+|in\s+)?',
            r'do\s+(we|you)\s+have\s+(any\s+)?books?\s+(by\s+|on\s+|about\s+|in\s+)?',
            r'books?\s+(by\s+|on\s+|about\s+)?',
            r'currently\s+have\s+in\s+this\s+library\s*\??',
            r'currently\s+have\s*\??',
            r'in\s+this\s+library\s*\??',
            r'in\s+the\s+library\s*\??',
            r'available\s+in\s+the\s+library\s*\??',
            r'available\s+in\s+this\s+library\s*\??',
            r'please\s*\??',
        ]
        for p in patterns:
            cleaned = re.sub(p, ' ', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'[\?\.!,;]', ' ', cleaned).strip()
        return cleaned

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
        rag_text: str = "",
        focus_book_meta: Optional[Dict[str, Any]] = None
    ) -> str:
        """Constructs high-accuracy, grounded system prompt with strict anti-hallucination guards."""
        active_style_prompt = STYLE_PROMPTS.get(chat_style, STYLE_PROMPTS['Balanced'])
        persona_lines = [
            "You are TARS, the Digital Librarian for Libre-Library at "
            "North Eastern Mindanao State University (NEMSU) – Tandag Campus (Surigao del Sur, Philippines).",
            "Assist students and faculty with high factual accuracy, clarity, and comprehensive academic depth.",
            f"STYLE: {active_style_prompt}",
            "",
            "CRITICAL ACCURACY & GROUNDING RULES:",
            "1. GROUNDING: Base answers strictly on facts from [DOCUMENT EVIDENCE] or [LIBRARY CATALOG HOLDINGS].",
            "2. NO FABRICATED SOURCES: NEVER invent or hallucinate document filenames or external book titles (e.g. do NOT invent fictional PDF names). Only cite documents actually listed in the provided evidence.",
            "3. HONEST REFUSAL: If the provided documents do not contain the answer, state clearly and honestly: 'The library documents do not contain information regarding [topic].' Do not guess or extrapolate.",
            "4. THOROUGH SUMMARIES: When asked to summarize or provide study notes, give a structured, comprehensive, and exhaustive breakdown covering all major concepts, principles, and categories present in the evidence."
        ]

        # Only inject inventory if non-empty (i.e. user explicitly inquired about catalog)
        if inventory and inventory.strip():
            persona_lines.append(f"\n{inventory.strip()}")

        if rag_text and rag_text.strip():
            persona_lines.append(f"\n{rag_text.strip()}")
            persona_lines.append("Cite sources/pages when referencing document knowledge (e.g. '[Source: title, Page X]').")

        if focus_book_meta:
            b_title = focus_book_meta.get('title') or focus_book_title or 'Untitled Document'

            # Author resolution
            authors_data = focus_book_meta.get('display_author') or focus_book_meta.get('authors')
            if isinstance(authors_data, list) and authors_data:
                b_author = authors_data[0].get('name', str(authors_data[0])) if isinstance(authors_data[0], dict) else str(authors_data[0])
            else:
                b_author = str(authors_data or 'Unknown Author')

            # Synopsis resolution (compact to prevent prompt bloat)
            synopsis_text = ""
            summaries = focus_book_meta.get('summaries')
            if summaries and isinstance(summaries, list) and summaries[0]:
                synopsis_text = str(summaries[0]).strip()
            elif focus_book_meta.get('description'):
                synopsis_text = str(focus_book_meta.get('description')).strip()

            if len(synopsis_text) > 400:
                synopsis_text = synopsis_text[:400] + "..."

            file_type = (focus_book_meta.get('file_type') or 'E-Book').upper()
            shelves = focus_book_meta.get('shelves', []) or []
            shelves_str = ", ".join(str(s) for s in shelves) if isinstance(shelves, list) else str(shelves)

            persona_lines.append(
                f"\n=== 🎯 CURRENTLY FOCUSED BOOK DETAILS (FROM LIBRARY CATALOG & PREVIEW) ===\n"
                f"- **Title:** {b_title}\n"
                f"- **Author(s):** {b_author}\n"
                f"- **Library Availability:** YES, this document is currently saved and available in the library archive ({file_type} format).\n"
                f"- **Shelf / Category:** {shelves_str or 'General Collection'}\n"
                f"- **Overview:** {synopsis_text or 'Ground answers on the document evidence.'}\n"
                f"Answer user inquiries about this document directly and accurately."
            )
        elif focus_book_title:
            persona_lines.append(f"\nFOCUS DOCUMENT: The user is asking about '{focus_book_title}'. Focus your answers on this document.")

        if teaching_mode:
            persona_lines.append("\nTEACHING MODE: Socratic teaching style. Guide the user with questions rather than immediate answers.")
        elif is_review_mode:
            persona_lines.append("\nCODE REVIEW MODE: Review provided code for architecture, performance, security, and cleanliness.")

        return "\n".join(persona_lines)

    @staticmethod
    async def _expand_adjacent_chunks(
        raw_hits: List[dict],
        query: str,
        focus_book_id: Optional[str] = None
    ) -> List[dict]:
        """
        Fast, high-precision adjacent window expansion.
        Expands multi-slide presentations, enumerated principles, and lists by at most 2 continuation
        pages, avoiding context bloat while ensuring complete multi-page coverage.
        """
        if not raw_hits:
            return raw_hits

        retrieved_pages_by_source: Dict[str, Set[int]] = {}
        for h in raw_hits:
            src = h.get('source', '')
            p = int(h.get('page') or 0)
            if p > 0:
                retrieved_pages_by_source.setdefault(src, set()).add(p)

        q_lower = query.lower()
        is_list_query = any(k in q_lower for k in (
            'what are', 'list', 'principle', 'type', 'level', 'step', 'phase', 'stage',
            'how many', 'explain the', 'all', '7', '6', '5', '4', '3', 'continue'
        ))

        target_source = None
        target_page = None
        target_bid = None
        needs_backward = False

        # Identify the primary sequential anchor chunk
        for h in raw_hits:
            p_val = int(h.get('page') or 0)
            if p_val <= 0:
                continue
            h_txt = h.get('text', '').lower()
            src = h.get('source', '')
            bid = h.get('book_id') or focus_book_id

            # Case A: Explicit list start (e.g. "1. Testing shows..." and ("2." or "principle"))
            if '1.' in h_txt and ('2.' in h_txt or any(k in h_txt for k in ('principle', 'step', 'phase', 'type', 'defect'))):
                target_source = src
                target_page = p_val
                target_bid = bid
                break

            # Case B: Mid-list hit on a numbered list query
            if is_list_query and any(m in h_txt for m in ('3.', '4.', '5.', '6.')) and not any(m in h_txt for m in ('1.', '2.')):
                target_source = src
                target_page = p_val
                target_bid = bid
                needs_backward = True
                break

            # Case C: Query asks for principles/types/levels and slide title introduces the topic
            if is_list_query and any(k in q_lower for k in ('principle', 'type', 'level', 'step')) and any(k in h_txt for k in ('principles of', 'types of', 'levels of')):
                if target_page is None:
                    target_source = src
                    target_page = p_val
                    target_bid = bid

        # Perform targeted continuation retrieval if anchor identified
        if target_page and target_source:
            already = retrieved_pages_by_source.get(target_source, set())
            pages_to_fetch = []
            if needs_backward and (target_page - 1) > 0 and (target_page - 1) not in already:
                pages_to_fetch.append(target_page - 1)
            for offset in (1, 2):
                cand = target_page + offset
                if cand not in already and cand not in pages_to_fetch:
                    pages_to_fetch.append(cand)

            if pages_to_fetch:
                adj_chunks = await run.io_bound(
                    tars_archive.get_chunks_by_pages,
                    target_bid,
                    target_source,
                    sorted(pages_to_fetch)
                )
                if adj_chunks:
                    # Keep anchor sequence + top other raw hits, up to 5 total chunks for fast TTFT
                    seq_pages = set([target_page] + pages_to_fetch)
                    selected_hits = [h for h in raw_hits if int(h.get('page') or 0) in seq_pages and h.get('source') == target_source]
                    selected_hits.extend(adj_chunks)

                    # Add top other hits not in sequence to retain catalog/document breadth
                    for h in raw_hits:
                        p = int(h.get('page') or 0)
                        if (h.get('source') != target_source or p not in seq_pages) and len(selected_hits) < 5:
                            selected_hits.append(h)

                    selected_hits.sort(key=lambda x: (x.get('source', ''), int(x.get('page') or 0)))
                    return selected_hits

        # Default fallback: return top 5 raw hits sorted by page
        capped_hits = list(raw_hits[:5])
        capped_hits.sort(key=lambda x: (x.get('source', ''), int(x.get('page') or 0)))
        return capped_hits

    @staticmethod
    async def perform_rag_search(
        text: str,
        focus_book_id: Optional[str] = None,
        focus_book_title: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Executes vector retrieval, multi-page document coverage sampling, and catalog routing.
        """
        rag_text = ""
        citations: List[Dict[str, Any]] = []
        try:
            clean_text = text.lower().strip()
            filter_source = None
            book_doc = None

            if focus_book_id:
                try:
                    book_doc = await mongo_db.get_book_details(focus_book_id)
                except Exception:
                    book_doc = None
                if book_doc:
                    resolved_p = mongo_db.resolve_document_path(focus_book_id, book_doc)
                    if resolved_p and Path(resolved_p).exists():
                        filter_source = Path(resolved_p).name
                    elif book_doc.get('local_path'):
                        filter_source = Path(book_doc.get('local_path')).name
                    else:
                        filter_source = focus_book_id
                elif focus_book_title:
                    filter_source = focus_book_title

            # Case 1: FOCUSED BOOK CONTEXT (Lecture / Book Active)
            if focus_book_id:
                is_sum = any(k in clean_text for k in SUMMARY_KEYWORDS)
                is_cont = any(k in clean_text for k in CONTINUE_KEYWORDS)

                start_p = 1
                if is_cont and history:
                    # Detect previously cited page numbers to advance continuation
                    found_pages = []
                    for m in history:
                        txt = m.get('content', '')
                        matches = re.findall(r'Page\s+(\d+)', txt, re.IGNORECASE)
                        for match in matches:
                            try:
                                found_pages.append(int(match))
                            except Exception:
                                pass
                    if found_pages:
                        start_p = max(found_pages) + 1

                raw_hits = []
                if is_sum or is_cont:
                    # Use chronological multi-page coverage chunks across the entire document
                    max_c = 12 if is_sum else 8
                    raw_hits = await run.io_bound(
                        tars_archive.get_document_coverage_chunks,
                        focus_book_id,
                        filter_source,
                        max_c,
                        start_p
                    )

                if not raw_hits:
                    # Standard targeted vector search with top_k = 6
                    raw_hits = await run.io_bound(
                        tars_archive.search_with_metadata,
                        text,
                        6,
                        filter_source,
                        focus_book_id
                    )
                    if raw_hits:
                        raw_hits = await ChatService._expand_adjacent_chunks(raw_hits, text, focus_book_id)

                if raw_hits:
                    rag_parts = []
                    for h in raw_hits:
                        src = h.get('source', 'Library Document')
                        p_val = h.get('page')
                        page_str = f" [Page {p_val}]" if p_val else ""
                        chunk_text = h.get('text', '')[:1500].strip()
                        rag_parts.append(f"[{src}{page_str}]:\n{chunk_text}")

                        cit_key = f"{src}_{p_val}"
                        if not any(c.get('key') == cit_key for c in citations):
                            citations.append({
                                "key": cit_key,
                                "source": src,
                                "title": h.get('title') or src,
                                "page": p_val,
                                "book_id": h.get('book_id') or focus_book_id
                            })
                    rag_text = "\n[DOCUMENT EVIDENCE]:\n" + "\n---\n".join(rag_parts)
                elif book_doc:
                    # Direct multi-page fallback using document structure or raw text
                    resolved_p = mongo_db.resolve_document_path(focus_book_id, book_doc)
                    if resolved_p and Path(resolved_p).exists():
                        try:
                            from core.utils.text_extractor import extract_document_structure, extract_text_from_file
                            sections = await run.io_bound(extract_document_structure, resolved_p)
                            if sections:
                                total_sec = len(sections)
                                if total_sec <= 10:
                                    picked = sections
                                else:
                                    step = (total_sec - 1) / 9.0
                                    picked = [sections[int(round(i * step))] for i in range(10)]
                                rag_parts = []
                                for s in picked:
                                    p_num = s.get('page', 1)
                                    s_txt = s.get('text', '')[:700].strip()
                                    if s_txt:
                                        rag_parts.append(f"[{Path(resolved_p).name} [Page {p_num}]]:\n{s_txt}")
                                        cit_key = f"{Path(resolved_p).name}_{p_num}"
                                        if not any(c.get('key') == cit_key for c in citations):
                                            citations.append({
                                                "key": cit_key,
                                                "source": Path(resolved_p).name,
                                                "title": book_doc.get('title') or Path(resolved_p).name,
                                                "page": p_num,
                                                "book_id": focus_book_id
                                            })
                                if rag_parts:
                                    rag_text = "\n[DOCUMENT EVIDENCE]:\n" + "\n---\n".join(rag_parts)
                            else:
                                file_text = await run.io_bound(extract_text_from_file, resolved_p)
                                if file_text and file_text.strip():
                                    excerpt = file_text[:2500].strip()
                                    rag_text = f"\n[DOCUMENT EXCERPT]:\n{excerpt}\n"
                                    citations.append({
                                        "key": f"{Path(resolved_p).name}_excerpt",
                                        "source": Path(resolved_p).name,
                                        "title": book_doc.get('title') or focus_book_title or Path(resolved_p).name,
                                        "page": 1,
                                        "book_id": focus_book_id
                                    })
                        except Exception as err:
                            logger.debug(f"Direct text excerpt fallback note: {err}")

            # Case 2: LIBRARY-WIDE CONTEXT (focus_book_id is None)
            else:
                # Check for catalog or author inquiry
                catalog_query = ChatService.extract_catalog_search_term(text)
                matched_books = []
                if catalog_query and len(catalog_query) >= 3:
                    matched_books = await mongo_db.books.search_books(catalog_query, limit=10)

                if matched_books:
                    lines = [f"Found {len(matched_books)} matching document(s) in the library catalog:"]
                    for b in matched_books:
                        b_title = b.get('title', 'Untitled')
                        authors = b.get('display_author') or b.get('authors', 'Unknown')
                        if isinstance(authors, list) and authors:
                            authors = authors[0].get('name', str(authors[0])) if isinstance(authors[0], dict) else str(authors[0])
                        ftype = (b.get('file_type') or 'E-Book').upper()
                        lines.append(f"- '{b_title}' by {authors} ({ftype})")
                        cit_key = str(b.get('id') or b.get('_id'))
                        citations.append({
                            "key": cit_key,
                            "source": b_title,
                            "title": b_title,
                            "page": 1,
                            "book_id": cit_key
                        })
                    rag_text = "\n[LIBRARY CATALOG HOLDINGS]:\n" + "\n".join(lines)
                else:
                    # General semantic passage search across whole library
                    raw_hits = await run.io_bound(tars_archive.search_with_metadata, text, 6, None, None)
                    if raw_hits:
                        raw_hits = await ChatService._expand_adjacent_chunks(raw_hits, text, None)
                    if raw_hits:
                        rag_parts = []
                        for h in raw_hits:
                            src = h.get('source', 'Library Document')
                            p_val = h.get('page')
                            page_str = f" [Page {p_val}]" if p_val else ""
                            chunk_text = h.get('text', '')[:1500].strip()
                            rag_parts.append(f"[{src}{page_str}]:\n{chunk_text}")

                            cit_key = f"{src}_{p_val}"
                            if not any(c.get('key') == cit_key for c in citations):
                                citations.append({
                                    "key": cit_key,
                                    "source": src,
                                    "title": h.get('title') or src,
                                    "page": p_val,
                                    "book_id": h.get('book_id') or ""
                                })
                        rag_text = "\n[DOCUMENT EVIDENCE]:\n" + "\n---\n".join(rag_parts)
        except Exception as e:
            logger.error(f"RAG Search Error: {e}")

        return rag_text, citations

    @staticmethod
    def build_messages_payload(system_persona: str, history: List[Dict[str, Any]], max_turns: int = 4) -> List[Dict[str, str]]:
        """Constructs and validates message payload for LLM streaming with token-efficient history pruning."""
        recent = (history or [])[-max_turns:]
        valid_history = []
        for m in recent:
            if not m or 'role' not in m or 'content' not in m:
                continue
            role = m['role']
            content = m['content'].strip()
            # Prevent compounding prompt lag while preserving core thoughts
            if role == 'assistant' and len(content) > 600:
                content = content[:580] + " ... [summary continued]"
            valid_history.append({"role": role, "content": content})
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
