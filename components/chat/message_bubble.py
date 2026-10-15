from nicegui import ui
from typing import Optional, List, Dict, Any, Callable, Tuple
from ui.pages.chat_service import STARTER_PROMPTS_BOOK, STARTER_PROMPTS_LIBRARY


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
    """Renders interactive citation chips linking to document reader."""
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
                    badge_row.classes('cursor-pointer hover:bg-indigo-100')
                    badge_row.on('click', lambda b=b_id: ui.navigate.to(f'/read/{b}'))
                    badge_row.tooltip("Click to open document in Reader")

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
    Returns: (card, status_label, message_md, copy_btn, tts_btn, citations_container)
    """
    with container:
        with ui.row().classes('w-full justify-start mb-4'):
            with ui.column().classes(
                'p-3.5 sm:p-5 bg-white border border-slate-200 '
                'rounded-2xl rounded-tl-sm shadow-sm max-w-[96%] sm:max-w-[85%] break-words w-full overflow-hidden'
            ) as card:
                # Assistant Header
                with ui.row().classes('w-full justify-between items-center mb-2.5 pb-2 border-b border-slate-100'):
                    with ui.row().classes('items-center gap-2'):
                        with ui.element('div').classes('p-1 sm:p-1.5 rounded-lg bg-indigo-50 text-indigo-600 border border-indigo-100'):
                            ui.icon('smart_toy', size='18px')
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

                message_md = ui.markdown(content).classes('text-sm text-slate-800 prose max-w-none break-words overflow-x-auto')

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
                'p-4 sm:p-5 rounded-3xl bg-indigo-50 text-indigo-600 '
                'border border-indigo-200 shadow-md mb-3 animate-pulse'
            ):
                ui.icon('smart_toy', size='3em')

            if focus_book_title:
                ui.label(f"Chatting with '{focus_book_title}'").classes('text-xl sm:text-2xl font-black text-slate-900 tracking-tight mb-1')
                ui.label("Ask questions, explore core themes, or test your comprehension of this document.").classes('text-xs sm:text-sm text-slate-500 max-w-lg mb-6')
                prompts = STARTER_PROMPTS_BOOK
            else:
                ui.label("TARS AI Digital Librarian").classes('text-xl sm:text-2xl font-black text-slate-900 tracking-tight mb-1')
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
