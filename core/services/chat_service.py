import logging
import re
import string
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)
from core.ai_engine.rag_pipeline import tars_archive
from core.config import RAG_MAX_DISTANCE

GREETING_KEYWORDS = {
    "hello",
    "hi",
    "hey",
    "tars",
    "yo",
    "greetings",
    "good morning",
    "good afternoon",
    "good evening",
    "howdy",
    "sup",
}

IDENTITY_KEYWORDS = {
    "who are you",
    "what are you",
    "identify",
    "your function",
    "introduce yourself",
    "what is your name",
    "who built you",
}

STYLE_PROMPTS = {
    'Balanced': "Provide a thorough, well-structured, and clear answer. Use headings, bullet points, and exact page citations.",
    'Concise': "Keep responses brief, direct, and high-signal without filler.",
    'Academic': "Use a scholarly, objective, and structured tone with clear terminology.",
    'Socratic': "Guide the user with clear explanations followed by a thought-provoking question.",
    'Exam Prep': "Provide an exam preparation study guide with key definitions, principles, and comparison tables."
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


def decompress_query_if_needed(text: str) -> str:
    """Restores whitespace if a user submits a continuous mashed query like 'Summarizethisbookbystartingfrom1toendto10'"""
    s = (text or "").strip()
    if len(s) > 12 and " " not in s:
        # Split camelCase / PascalCase
        spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
        # Split digits
        spaced = re.sub(r"([a-zA-Z])(\d+)", r"\1 \2", spaced)
        spaced = re.sub(r"(\d+)([a-zA-Z])", r"\1 \2", spaced)
        # Split common English keywords if still compressed
        kw = (
            "summarize", "summary", "overview", "explain", "tell", "give", "describe",
            "this", "the", "book", "novel", "story", "chapter", "chapters", "text",
            "by", "starting", "start", "from", "to", "end", "and", "in", "about"
        )
        for w in kw:
            pattern = re.compile(re.escape(w), re.IGNORECASE)
            spaced = pattern.sub(f" {w} ", spaced)
        cleaned = " ".join(spaced.split())
        if len(cleaned.split()) >= 2:
            return cleaned
    return s


class ChatService:
    """Orchestrates intent detection, grounded RAG assembly, and anti-hallucination prompts."""

    @staticmethod
    def _normalize_text(text: str) -> str:
        cleaned = re.sub(r"[^\w\s]", " ", (text or "").lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    def is_greeting_or_identity(self, text: str) -> bool:
        """Returns True if the prompt is purely a greeting or identity inquiry."""
        norm = self._normalize_text(text)
        if not norm:
            return False

        # Exact match or short greeting phrase (<= 6 words)
        words = norm.split()
        if norm in GREETING_KEYWORDS:
            return True
        if len(words) <= 5 and any(
            norm == g or norm.startswith(f"{g} ") or norm.endswith(f" {g}")
            for g in GREETING_KEYWORDS
        ):
            # Ensure no substantive question words follow the greeting
            question_markers = {"explain", "summarize", "what is", "how does", "chapter", "page", "book", "define"}
            if not any(q in norm for q in question_markers):
                return True

        if any(ident in norm for ident in IDENTITY_KEYWORDS) and len(words) <= 10:
            return True

        return False

    def should_skip_rag(self, text: str) -> bool:
        """Skips ChromaDB lookup for greetings, identity checks, or empty inputs."""
        if not text or not text.strip():
            return True
        return self.is_greeting_or_identity(text)

    async def perform_rag_search(
        self,
        query: str,
        focus_book_id: Optional[str] = None,
        focus_book_title: Optional[str] = None,
        top_k: int = 4,
        max_distance: float = RAG_MAX_DISTANCE,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Executes thresholded vector retrieval, dynamic alias resolution across MongoDB and ChromaDB,
        expands adjacent chunks, injects verified catalog synopses, and formats verified [DOCUMENT EVIDENCE].
        """
        if self.should_skip_rag(query):
            return "", []

        normalized_query = decompress_query_if_needed(query)

        # 1. Dynamically resolve book aliases and verified synopsis from MongoDB
        book = None
        if focus_book_id:
            try:
                from core.database.mongo_manager import mongo_db
                if mongo_db.db is not None:
                    book = await mongo_db.books.get_book_by_id(focus_book_id)
            except Exception as e:
                logger.debug("Mongo book lookup by id notice: %s", e)

        if not book and focus_book_title:
            try:
                from core.database.mongo_manager import mongo_db
                if mongo_db.db is not None:
                    book = await mongo_db.books.get_book_by_title(focus_book_title)
            except Exception as e:
                logger.debug("Mongo book lookup by title notice: %s", e)

        candidate_ids: List[str] = []
        candidate_sources: List[str] = []
        verified_synopsis = ""
        effective_title = focus_book_title or "Library Document"

        if book:
            effective_title = book.get("title") or effective_title
            candidate_ids.append(str(book.get("_id")))
            if book.get("id"):
                candidate_ids.append(str(book.get("id")))
            if book.get("title"):
                candidate_sources.append(book["title"])
            if book.get("local_path"):
                candidate_sources.append(Path(book["local_path"]).name)
            for p in (book.get("formats") or {}).values():
                if isinstance(p, str):
                    candidate_sources.append(Path(p).name)
            verified_synopsis = (book.get("description") or "").strip()

        if focus_book_title and focus_book_title not in candidate_sources:
            candidate_sources.append(focus_book_title)
        if focus_book_id and focus_book_id not in candidate_ids:
            candidate_ids.append(focus_book_id)

        # 2. Check for broad or summary intents
        norm_q = normalized_query.lower()
        is_broad = any(k in norm_q for k in (
            "summarize", "summary", "overview", "all topics", "lecture", "study guide",
            "explain all", "all slides", "continue", "breakdown", "chapter", "starting from",
            "start from", "1 to", "10"
        ))
        target_max_chars = 7500 if is_broad else 3500

        # 3. Query ChromaDB with full candidate list
        primary_chunks = tars_archive.search_with_metadata(
            query=normalized_query,
            top_k=top_k,
            filter_source=candidate_sources[0] if candidate_sources else focus_book_title,
            book_id=candidate_ids[0] if candidate_ids else focus_book_id,
            candidate_sources=candidate_sources,
            candidate_book_ids=candidate_ids,
            fallback_to_library=False,
            max_distance=max_distance,
        )

        # For broad/summary inquiries on focused documents, fetch introductory narrative chunks
        if is_broad and (candidate_ids or candidate_sources):
            intro_chunks = tars_archive.get_book_intro_chunks(
                book_id=candidate_ids[0] if candidate_ids else None,
                candidate_sources=candidate_sources,
                limit=4,
            )
            seen_texts = set(c.get("text", "")[:60] for c in primary_chunks)
            for ic in intro_chunks:
                t_snip = ic.get("text", "")[:60]
                if t_snip not in seen_texts:
                    seen_texts.add(t_snip)
                    primary_chunks.append(ic)

        evidence_blocks: List[str] = []
        citations: List[Dict[str, Any]] = []
        seen_citations = set()

        # Inject verified catalog synopsis if available for broad/summary questions or when chunks are limited
        if verified_synopsis and (is_broad or not primary_chunks):
            synopsis_header = f"[Source: {effective_title}, Verified Catalog Synopsis]"
            evidence_blocks.append(f"{synopsis_header}\n{verified_synopsis}")
            citations.append({
                "source": str(effective_title),
                "page": "Catalog Synopsis",
                "book_id": candidate_ids[0] if candidate_ids else focus_book_id,
                "distance": 0.0,
            })

        if not primary_chunks and not evidence_blocks:
            return "", []

        expanded_chunks = self._expand_adjacent_chunks(primary_chunks, max_chars=target_max_chars) if primary_chunks else []

        for item in expanded_chunks:
            meta = item.get("metadata") or {}
            source_title = (
                meta.get("title")
                or effective_title
                or meta.get("source")
                or "Library Document"
            )
            page_num = meta.get("page") or meta.get("page_number") or "N/A"
            text_body = (item.get("text") or "").strip()
            if not text_body:
                continue

            author = meta.get("author")
            author_part = f" | Author: {author}" if author and author != "Unknown Author" else ""
            header = f"[Source: {source_title}{author_part}, Page {page_num}]"
            evidence_blocks.append(f"{header}\n{text_body}")

            cite_key = (str(source_title), str(page_num))
            if cite_key not in seen_citations:
                seen_citations.add(cite_key)
                citations.append(
                    {
                        "source": str(source_title),
                        "page": page_num,
                        "book_id": meta.get("book_id") or (candidate_ids[0] if candidate_ids else focus_book_id),
                        "distance": item.get("distance", 0.0),
                    }
                )

        if not evidence_blocks:
            return "", []

        rag_text = (
            "[DOCUMENT EVIDENCE]\n"
            + "\n\n---\n\n".join(evidence_blocks)
            + "\n[/DOCUMENT EVIDENCE]"
        )
        return rag_text, citations

    def _expand_adjacent_chunks(self, chunks: List[dict], max_chars: int = 3500) -> List[dict]:
        """Merges adjacent sequence chunks while deduplicating and respecting max_chars."""
        collected: List[dict] = []
        seen_keys = set()
        total_chars = 0

        for chunk in chunks:
            meta = chunk.get("metadata") or {}
            book_id = meta.get("book_id")
            source = meta.get("source")
            c_idx = meta.get("chunk_index")

            neighbors = [chunk]
            if isinstance(c_idx, int):
                adj = tars_archive.get_adjacent_chunks(
                    book_id=book_id,
                    source=source,
                    chunk_index=c_idx,
                    window=1,
                )
                neighbors.extend(adj)

            neighbors.sort(key=lambda x: (x.get("metadata") or {}).get("chunk_index", 0))

            for item in neighbors:
                m = item.get("metadata") or {}
                dedup_key = (
                    m.get("book_id") or m.get("source") or "",
                    m.get("page") or m.get("page_number") or "",
                    m.get("chunk_index", item.get("text", "")[:64]),
                )
                if dedup_key in seen_keys:
                    continue
                text_len = len(item.get("text") or "")
                if total_chars + text_len > max_chars and collected:
                    break
                seen_keys.add(dedup_key)
                collected.append(item)
                total_chars += text_len

        return collected

    def build_system_persona(
        self,
        chat_style: str = "Academic",
        focus_book: Optional[Dict[str, Any]] = None,
        is_greeting: bool = False,
        focus_book_meta: Optional[Dict[str, Any]] = None,
        focus_book_title: Optional[str] = None,
        teaching_mode: bool = False,
        is_review_mode: bool = False,
        inventory: str = "",
        rag_text: str = "",
    ) -> str:
        """
        Synthesizes the system persona with anti-hallucination constraints.
        Suppresses forced book summary instructions when is_greeting=True.
        """
        style_directives = {
            "Academic": "Use a scholarly, objective, and structured tone with clear terminology.",
            "Concise": "Keep responses brief, direct, and high-signal without filler.",
            "Socratic": "Guide the user with clear explanations followed by a thought-provoking question.",
            "Balanced": "Provide a thorough, well-structured, and clear answer with exact citations.",
            "Exam Prep": "Provide an exam preparation study guide with key definitions and principles."
        }
        chosen_style = style_directives.get(chat_style, style_directives.get("Academic"))

        target_book = focus_book or focus_book_meta
        eff_focus_title = (target_book.get("title") if target_book else None) or focus_book_title

        rule_5 = (
            f"5. STRICT FOCUS BOOK GROUNDING: The user has '{eff_focus_title}' focused. You MUST base all answers, summaries, plot descriptions, and character details SOLELY on the verified [DOCUMENT EVIDENCE] and catalog synopsis provided above. If the document excerpts do not contain details requested by the user, state clearly: 'The library archive for {eff_focus_title} does not contain explicit excerpts for [detail].' You are strictly forbidden from inventing or hallucinating characters, events, or plot points from outside the verified text."
            if eff_focus_title
            else "5. GENERAL INQUIRIES: If no document evidence is provided and user asks a general inquiry, answer accurately from general knowledge while clarifying it is not drawn from library holdings."
        )

        lines = [
            "You are TARS, the Digital Librarian and AI Research & Library Assistant for Libre-Library.",
            f"STYLE DIRECTIVE: {chosen_style}",
            "",
            "CRITICAL ACCURACY & ANTI-HALLUCINATION RULES:",
            "1. DIRECT ANSWER FIRST: Begin immediately with the direct, factual answer and key citations in the first 1-2 sentences. Do NOT include filler pleasantries or meta-preambles (such as 'Based on the provided documents...', 'Sure! I can help with that', or 'According to the text...').",
            "2. STRICT CLASSIFICATION FIDELITY: Meticulously follow category hierarchies in [DOCUMENT EVIDENCE]. Do NOT conflate or swap attributes between categories.",
            "3. GROUNDING & VERIFIED CITATIONS: ONLY cite pages explicitly present in brackets (e.g. '[Source: title, Page X]'). NEVER invent or assume page numbers or source titles.",
            "4. HONEST REFUSAL: If the provided documents do not contain the answer, state clearly: 'The library documents do not contain information regarding [topic].' Do not guess or fabricate unstated claims.",
            rule_5,
        ]

        # Resolve book details from either focus_book or focus_book_meta
        if target_book:
            title = target_book.get("title") or focus_book_title or "Selected Document"
            author = (
                target_book.get("author")
                or target_book.get("display_author")
                or "Unknown Author"
            )
            if isinstance(author, list) and author:
                author = author[0].get("name", str(author[0])) if isinstance(author[0], dict) else str(author[0])
            category = (
                target_book.get("category")
                or (target_book.get("shelves")[0] if target_book.get("shelves") and isinstance(target_book.get("shelves"), list) else None)
                or "General"
            )
            desc = target_book.get("description") or ""

            if is_greeting:
                lines.extend(
                    [
                        "",
                        f"NOTE: The user currently has '{title}' by {author} open in their workspace. "
                        "Greet the user naturally and briefly mention you are ready to help if they have questions about it. "
                        "Do NOT summarize or recite details about the book unless asked.",
                    ]
                )
            else:
                lines.extend(
                    [
                        "",
                        "=== CURRENTLY FOCUSED BOOK DETAILS ===",
                        f"Title: {title}",
                        f"Author: {author}",
                        f"Category: {category}",
                    ]
                )
                if desc:
                    lines.append(f"Description: {desc[:400]}")
                if target_book.get("file_type"):
                    lines.append(f"Availability: YES, this document is currently saved and available in the library archive ({target_book.get('file_type')} format).")
                if target_book.get("shelves") and isinstance(target_book.get("shelves"), list):
                    lines.append(f"Shelves: {', '.join(target_book.get('shelves'))}")
                lines.append("Prioritize [DOCUMENT EVIDENCE] from this focused document when answering the user's inquiry.")
        elif focus_book_title:
            if is_greeting:
                lines.extend([
                    "",
                    f"NOTE: The user currently has '{focus_book_title}' open in their workspace. "
                    "Greet the user naturally and briefly mention you are ready to help if they have questions about it. "
                    "Do NOT summarize or recite details about the book unless asked."
                ])
            else:
                lines.extend([
                    "",
                    "=== CURRENTLY FOCUSED BOOK DETAILS ===",
                    f"Title: {focus_book_title}",
                    "Prioritize [DOCUMENT EVIDENCE] from this focused document when answering the user's inquiry."
                ])

        if inventory and inventory.strip():
            lines.append(f"\n{inventory.strip()}")

        if rag_text and rag_text.strip():
            lines.append(f"\n{rag_text.strip()}")

        if teaching_mode:
            lines.append("\nTEACHING MODE: Socratic teaching style. Guide the user with questions rather than immediate answers.")
        elif is_review_mode:
            lines.append("\nCODE REVIEW MODE: Review provided code for architecture, performance, security, and cleanliness.")

        return "\n".join(lines)

    def build_messages_payload(
        self,
        system_persona: str,
        history: Optional[List[Dict[str, Any]]] = None,
        current_query: Optional[str] = None,
        rag_text: str = "",
        max_turns: int = 6,
    ) -> List[Dict[str, str]]:
        """
        Assembles the OpenAI/Llama.cpp chat completion payload.
        - Deduplicates the trailing user message if MongoDB persisted it before history fetch.
        - Wraps [DOCUMENT EVIDENCE] inside the active user turn to prevent system prompt attention dilution.
        """
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_persona.strip()}
        ]

        cleaned_history: List[Dict[str, str]] = []
        for item in history or []:
            role = item.get("role")
            content = (item.get("content") or item.get("text") or "").strip()
            if role in ("user", "assistant") and content:
                cleaned_history.append({"role": role, "content": content})

        # Deduplicate trailing user turn if background DB write already saved current_query
        if current_query and cleaned_history:
            last_msg = cleaned_history[-1]
            if (
                last_msg["role"] == "user"
                and last_msg["content"].strip() == current_query.strip()
            ):
                cleaned_history.pop()

        # Keep bounded conversation history (max_turns pairs = max_turns * 2 messages)
        if max_turns > 0:
            cleaned_history = cleaned_history[-(max_turns * 2) :]
        else:
            cleaned_history = []

        messages.extend(cleaned_history)

        # Anchor active query with user-turn RAG evidence
        if current_query and current_query.strip():
            if rag_text and rag_text.strip():
                user_msg_content = (
                    f"{rag_text.strip()}\n\n[USER INQUIRY]:\n{current_query.strip()}"
                )
            else:
                user_msg_content = current_query.strip()
            messages.append({"role": "user", "content": user_msg_content})

        return messages

    @staticmethod
    def group_sessions_chronologically(sessions: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
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
    def export_chat_markdown(messages: List[Dict[str, Any]], focus_book_title: Optional[str], session_id: str) -> str:
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


chat_service = ChatService()
group_sessions_chronologically = ChatService.group_sessions_chronologically
