import html
import re
from typing import Optional, List, Dict, Any, Callable, Tuple
from urllib.parse import quote_plus
from nicegui import ui
from core.services.chat_service import STARTER_PROMPTS_BOOK, STARTER_PROMPTS_LIBRARY

CITATION_TAG_REGEX = re.compile(
    r"\[(?:"
    r"(?:Book\s*:\s*(?P<title1>[^\]|]+?)\s*\|\s*Page\s*:?\s*(?P<page1>\d+))"
    r"|(?:Source\s*(?P<src_idx>\d+)\s*(?:,|\|)\s*Page\s*:?\s*(?P<page2>\d+))"
    r"|(?:Source\s*:\s*(?P<title3>[^,\]]+?)\s*,\s*Page\s*:?\s*(?P<page4>\d+))"
    r"|(?P<title2>[^,\]]+?)\s*,\s*p(?:age|\.)?\s*(?P<page3>\d+)"
    r")\]",
    re.IGNORECASE,
)


def _normalize_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _extract_highlight_snippet(chunk_text: str, max_words: int = 8) -> str:
    if not chunk_text:
        return ""
    lines = [
        line.strip()
        for line in chunk_text.splitlines()
        if line.strip() and not (line.strip().startswith("[") and line.strip().endswith("]"))
    ]
    body = " ".join(lines) if lines else chunk_text
    words = re.findall(r"[A-Za-z0-9\-]+", body)
    return " ".join(words[:max_words])


def build_deep_link_url(chunk_meta: Dict[str, Any], chunk_text: str = "") -> str:
    """Constructs format-aware deep links to exact reader coordinates with highlight query."""
    book_id = quote_plus(str(chunk_meta.get("book_id", "")))
    doc_format = str(chunk_meta.get("format", "PDF")).upper()
    page = chunk_meta.get("page") or chunk_meta.get("page_number")
    cfi = chunk_meta.get("cfi") or chunk_meta.get("epub_cfi")
    snippet = _extract_highlight_snippet(chunk_text)
    encoded_snippet = quote_plus(snippet) if snippet else ""

    if doc_format == "EPUB" and cfi:
        url = f"/read/{book_id}?cfi={quote_plus(str(cfi))}"
        if encoded_snippet:
            url += f"&highlight={encoded_snippet}"
        return url

    if doc_format in ("DOCX", "PPTX", "TXT", "MD"):
        if encoded_snippet:
            return f"/read/{book_id}?highlight={encoded_snippet}"
        return f"/read/{book_id}"

    target_page = int(page) if page and str(page).isdigit() else 1
    url = f"/read/{book_id}?page={target_page}"
    if encoded_snippet:
        url += f"&highlight={encoded_snippet}"
    return url


def linkify_tars_citations(
    llm_response_html: str,
    retrieved_chunks: List[Dict[str, Any]],
) -> str:
    """
    Deterministically transforms natural citation tags ([Book: ... | Page 84]) into active,
    verified NiceGUI/HTML hyperlinks with zero LLM hallucination risk.
    """
    if not llm_response_html or not retrieved_chunks:
        return llm_response_html

    by_title_and_page: Dict[tuple, Dict[str, Any]] = {}
    by_title_only: Dict[str, Dict[str, Any]] = {}
    by_source_index: Dict[int, Dict[str, Any]] = {}

    for idx, chunk in enumerate(retrieved_chunks, start=1):
        meta = chunk.get("metadata") or chunk
        book_id = meta.get("book_id")
        if not book_id:
            continue

        title = meta.get("title") or meta.get("book_title") or meta.get("source") or f"Source {idx}"
        norm_title = _normalize_key(title)
        page_val = meta.get("page") or meta.get("page_number") or 1
        try:
            page_int = int(page_val)
        except (ValueError, TypeError):
            page_int = 1

        entry = {
            "book_id": str(book_id),
            "title": title,
            "page": page_int,
            "format": meta.get("format", "PDF"),
            "cfi": meta.get("cfi"),
            "text": chunk.get("text", ""),
        }
        by_source_index[idx] = entry
        by_title_and_page[(norm_title, page_int)] = entry
        by_title_only.setdefault(norm_title, entry)

    def _replace_match(match: re.Match) -> str:
        src_idx_str = match.group("src_idx")
        raw_title = (match.group("title1") or match.group("title2") or match.group("title3") or "").strip()
        raw_page = match.group("page1") or match.group("page2") or match.group("page3") or match.group("page4")
        page_num = int(raw_page) if raw_page and raw_page.isdigit() else 1

        matched_entry: Optional[Dict[str, Any]] = None

        if src_idx_str and src_idx_str.isdigit():
            matched_entry = by_source_index.get(int(src_idx_str))

        if not matched_entry and raw_title:
            norm_t = _normalize_key(raw_title)
            matched_entry = by_title_and_page.get((norm_t, page_num))
            if not matched_entry:
                for stored_norm, candidate in by_title_only.items():
                    if norm_t in stored_norm or stored_norm in norm_t:
                        matched_entry = dict(candidate)
                        matched_entry["page"] = page_num
                        break

        if not matched_entry and len(by_source_index) == 1:
            matched_entry = dict(by_source_index[1])
            matched_entry["page"] = page_num

        if not matched_entry:
            return match.group(0)

        target_meta = {
            "book_id": matched_entry["book_id"],
            "page": page_num,
            "format": matched_entry.get("format", "PDF"),
            "cfi": matched_entry.get("cfi"),
        }
        href = build_deep_link_url(target_meta, matched_entry.get("text", ""))
        safe_title = html.escape(matched_entry["title"])
        return (
            f'<a href="{href}" class="tars-citation-chip" '
            f'title="Open {safe_title} at Page {page_num}">'
            f"📖 {safe_title} — p. {page_num}</a>"
        )

    return CITATION_TAG_REGEX.sub(_replace_match, llm_response_html)


CITATION_CHIP_CSS = """
<style>
.tars-citation-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.15rem 0.55rem;
    margin: 0.1rem 0.2rem;
    border-radius: 999px;
    background: rgba(14, 165, 233, 0.15);
    border: 1px solid rgba(56, 189, 248, 0.45);
    color: #0284c7 !important;
    font-size: 0.82rem;
    font-weight: 600;
    text-decoration: none !important;
    white-space: nowrap;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    vertical-align: middle;
    transition: background 0.15s ease, transform 0.12s ease;
}
.tars-citation-chip:hover {
    background: rgba(14, 165, 233, 0.28);
    transform: translateY(-1px);
    color: #0369a1 !important;
}
</style>
"""


def setup_message_actions(content: str, copy_btn, tts_btn) -> None:
    """Binds 1-click clipboard copy and text-to-speech audio playback."""
    if not content or not copy_btn or not tts_btn:
        return

    try:
        # Check if client was deleted
        if hasattr(copy_btn, '_client') and (copy_btn._client() is None or getattr(copy_btn._client(), '_deleted', False)):
            return

        # Clipboard action
        copy_btn.on('click', lambda c=content: (
            ui.run_javascript(f"navigator.clipboard.writeText({repr(c)});"),
            ui.notify("Response copied to clipboard!", type='positive')
        ))

        # Text-to-speech action
        clean_text = content.replace("`", "").replace("*", "").replace("#", "")
        tts_btn.on('click', lambda c=clean_text: ui.run_javascript(f"""
            if (window.speechSynthesis.speaking) {{
                window.speechSynthesis.cancel();
            }} else {{
                const u = new SpeechSynthesisUtterance({repr(c[:1500])});
                u.rate = 1.0;
                window.speechSynthesis.speak(u);
            }}
        """))
    except Exception:
        pass


def render_citation_chips(citations: list, container) -> None:
    """Renders interactive citation chips linking directly to document reader coordinates."""
    if not container or not citations:
        return

    try:
        # Check if the element's client is still alive
        if hasattr(container, '_client') and (container._client() is None or getattr(container._client(), '_deleted', False)):
            return

        container.set_visibility(True)
        with container:
            ui.label("Sources & Citations:").classes('text-[10px] font-bold uppercase tracking-wider text-slate-400')
            for cit in citations:
                label_txt = cit.get('title') or cit.get('source', 'Document')
                if len(label_txt) > 28:
                    label_txt = label_txt[:28] + '...'
                if cit.get('page'):
                    label_txt += f" (p.{cit['page']})"

                b_id = cit.get('book_id')
                badge_row = ui.row().classes(
                    'items-center gap-1 px-2.5 py-0.5 rounded-full bg-indigo-50 '
                    'border border-indigo-200 text-[11px] text-indigo-700 '
                    'font-semibold shadow-sm transition-all hover:scale-105'
                )
                if b_id:
                    deep_href = build_deep_link_url(cit, cit.get('text', ''))
                    badge_row.classes('cursor-pointer hover:bg-indigo-100')
                    badge_row.on('click', lambda h=deep_href: ui.navigate.to(h))
                    badge_row.tooltip("Click to open document at cited page")

                with badge_row:
                    ui.icon('menu_book' if b_id else 'description', size='12px').classes('text-indigo-500')
                    ui.label(label_txt)
    except Exception:
        return


def render_user_message(container, text: str) -> None:
    """Renders user message bubble with modern indigo gradient and rounded styling."""
    with container:
        with ui.row().classes('w-full justify-end mb-4'):
            with ui.row().classes('items-start gap-2 max-w-[90%] sm:max-w-[78%] justify-end'):
                with ui.column().classes('p-3.5 sm:p-4 bg-gradient-to-r from-indigo-600 to-indigo-700 text-white rounded-2xl rounded-tr-sm shadow-md max-w-full overflow-hidden'):
                    ui.label(text).classes('text-sm text-white break-words')


def render_assistant_message(
    container,
    content: str = "",
    citations: list = None,
    in_progress: bool = False,
    teaching_mode: bool = False
) -> Tuple[Any, Any, Any, Any, Any, Any]:
    """
    Renders assistant message card with avatar, model badge, 1-click copy, TTS, and citations.
    Applies deterministic linkify_tars_citations to convert citation tags to deep-linking reader links.
    Returns: (card, status_label, message_md, copy_btn, tts_btn, citations_container)
    """
    with container:
        ui.add_head_html(CITATION_CHIP_CSS)
        with ui.row().classes('w-full justify-start mb-4'):
            with ui.column().classes(
                'p-3.5 sm:p-5 bg-white border border-slate-200 '
                'rounded-2xl rounded-tl-sm shadow-sm max-w-[96%] sm:max-w-[85%] break-words w-full overflow-hidden'
            ) as card:
                # Assistant Header
                with ui.row().classes('w-full justify-between items-center mb-2.5 pb-2 border-b border-slate-100'):
                    with ui.row().classes('items-center gap-2'):
                        with ui.element('div').classes('w-6 h-6 rounded-lg bg-cyan-50 flex items-center justify-center border border-cyan-100 p-0.5 shrink-0 shadow-2xs'):
                            ui.image('/static/tars_icon.svg').classes('w-full h-full object-contain').props('no-spinner')
                        ui.label('TARS AI').classes('text-xs font-bold text-slate-900')
                        ui.label('Librarian').classes('text-[10px] font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-full border border-indigo-100')
                        if teaching_mode:
                            ui.label('Socratic Tutor').classes('text-[10px] font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200')

                    with ui.row().classes('items-center gap-1'):
                        tts_btn = ui.button(icon='volume_up').props('flat round dense size=xs color=grey-7').tooltip('Read Aloud (TTS)')
                        copy_btn = ui.button(icon='content_copy').props('flat round dense size=xs color=grey-7').tooltip('Copy Response')

                status_label = None
                if in_progress:
                    status_label = ui.label("Consulting archives...").classes('text-xs text-indigo-600 animate-pulse font-medium mb-1')

                display_content = linkify_tars_citations(content, citations or []) if citations else content
                message_md = ui.markdown(display_content).classes('text-sm text-slate-800 prose max-w-none break-words overflow-x-auto')

                if not in_progress and content:
                    setup_message_actions(content, copy_btn, tts_btn)

                citations_container = ui.row().classes('gap-1.5 mt-3 pt-2.5 border-t border-slate-100 flex-wrap items-center')
                if citations:
                    render_citation_chips(citations, citations_container)
                else:
                    citations_container.set_visibility(False)

                return card, status_label, message_md, copy_btn, tts_btn, citations_container


def render_welcome_state(
    container,
    focus_book_title: Optional[str] = None,
    on_preset_click: Optional[Callable[[str], Any]] = None
) -> ui.column:
    """Displays a rich greeting hero and starter prompt cards strictly inside container."""
    if not container:
        return None

    container.clear()
    with container:
        welcome_col = ui.column().classes('w-full items-center justify-center py-8 sm:py-12 text-center')
        with welcome_col:
            with ui.element('div').classes(
                'p-3.5 sm:p-4 rounded-3xl bg-cyan-50/80 '
                'border border-cyan-200/80 shadow-md mb-4 flex items-center justify-center hover:scale-105 transition-transform'
            ):
                ui.image('/static/tars_icon.svg').classes('w-16 h-16 sm:w-20 sm:h-20 object-contain').props('no-spinner')

            if focus_book_title:
                ui.label(f"Chatting with '{focus_book_title}'").classes('text-xl sm:text-2xl font-black text-slate-900 tracking-tight mb-1')
                ui.label("Ask questions, explore core themes, or test your comprehension of this document.").classes('text-xs sm:text-sm text-slate-500 max-w-lg mb-6')
                prompts = STARTER_PROMPTS_BOOK
            else:
                ui.image('/static/tars_logo.svg').classes('h-10 sm:h-12 w-auto object-contain mb-2').props('no-spinner')
                ui.label("Your intelligent companion for research, synthesis, and deep learning across your library.").classes('text-xs sm:text-sm text-slate-500 max-w-lg mb-6')
                prompts = STARTER_PROMPTS_LIBRARY

            with ui.grid().classes('w-full max-w-2xl grid-cols-1 sm:grid-cols-2 gap-2.5 sm:gap-3 text-left'):
                for label, prompt_text in prompts:
                    with ui.card().classes(
                        'p-3.5 sm:p-4 rounded-2xl bg-white border border-slate-200 '
                        'shadow-sm hover:shadow-md hover:border-indigo-400 '
                        'hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group'
                    ).on('click', lambda p=prompt_text: on_preset_click(p) if on_preset_click else None):
                        with ui.row().classes('items-center justify-between w-full mb-1'):
                            ui.label(label).classes('text-xs font-bold text-indigo-600')
                            ui.icon('arrow_forward', size='14px').classes('text-slate-300 group-hover:text-indigo-500 group-hover:translate-x-1 transition-all')
                        ui.label(prompt_text).classes('text-[11px] sm:text-xs text-slate-500 font-medium line-clamp-2 leading-snug')

        return welcome_col
