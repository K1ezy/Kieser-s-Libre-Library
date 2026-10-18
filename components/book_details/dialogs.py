from nicegui import ui
from typing import Dict, Any, Callable
from core.auth.jwt_handler import get_current_user_role
from core.services.book_details_service import book_details_service


def open_cover_dialog(title: str, cover_url: str):
    """Cover zoom lightbox preview modal."""
    with ui.dialog() as cover_dialog, ui.card().classes(
        'p-4 sm:p-5 bg-white/95 backdrop-blur-md rounded-3xl max-w-lg w-full items-center shadow-2xl border border-slate-200'
    ):
        with ui.row().classes('w-full justify-between items-center px-1 pb-3 border-b border-slate-100'):
            with ui.column().classes('gap-0 max-w-[80%]'):
                ui.label(title).classes('font-bold text-slate-800 text-sm sm:text-base truncate')
                ui.label('Front Page Cover Preview').classes('text-xs text-indigo-600 font-semibold')
            ui.button(icon='close', on_click=cover_dialog.close).props('flat round dense size=sm color=grey')
        with ui.element('div').classes('w-full max-h-[72vh] flex items-center justify-center overflow-hidden rounded-2xl my-3 bg-slate-50 border border-slate-100 shadow-inner'):
            ui.image(cover_url).classes('max-h-[70vh] object-contain rounded-xl shadow-md')
        with ui.row().classes('w-full justify-end pt-1'):
            ui.button('Close', on_click=cover_dialog.close).props('unelevated rounded-xl size=sm color=indigo font-bold')
    cover_dialog.open()


def open_edit_metadata_dialog(book_id: str, book: Dict[str, Any], on_saved: Callable[[Dict[str, Any]], None]):
    """Edit Book Metadata Dialog (Librarian & Admin Restricted)."""
    if get_current_user_role() not in ('admin', 'librarian'):
        ui.notify("Librarian or Administrator privileges required to edit book metadata.", type='warning')
        return

    title = book.get('title', 'Untitled')
    author_name = book.get('display_author') or (book.get('authors', ['Unknown'])[0] if book.get('authors') else 'Unknown')
    shelves = book.get('shelves', []) or []
    genres = book.get('genres', []) or book.get('subjects', []) or []
    publisher = book.get('publisher') or ""
    pub_year = book.get('publication_year') or ""
    synopsis_text = book.get('description') or ""

    with ui.dialog() as edit_dialog, ui.card().classes(
        'w-[calc(100vw-2rem)] max-w-2xl p-5 sm:p-6 bg-white rounded-3xl shadow-2xl border border-slate-200 max-h-[90vh] flex flex-col'
    ):
        with ui.row().classes('w-full justify-between items-center pb-3 border-b border-slate-100'):
            with ui.row().classes('items-center gap-2'):
                with ui.element('div').classes('p-2 rounded-xl bg-indigo-50 text-indigo-600'):
                    ui.icon('edit_note', size='20px')
                ui.label('Edit Book Metadata').classes('text-lg font-black text-slate-900')
            ui.button(icon='close', on_click=edit_dialog.close).props('flat round dense size=sm color=grey')

        with ui.column().classes('w-full gap-3.5 py-4 overflow-y-auto flex-grow no-scrollbar'):
            title_input = ui.input(label='Title', value=title).props('outlined dense rounded').classes('w-full')
            author_input = ui.input(label='Author(s)', value=author_name if author_name != 'Unknown' else '').props('outlined dense rounded').classes('w-full')
            
            with ui.row().classes('w-full gap-3 flex-col sm:flex-row'):
                shelves_val = ", ".join(shelves) if isinstance(shelves, list) else str(shelves)
                shelves_input = ui.input(label='Shelf / Category', value=shelves_val).props('outlined dense rounded').classes('flex-1')
                
                tags_val = ", ".join(genres) if isinstance(genres, list) else str(genres)
                tags_input = ui.input(label='Tags / Genres (comma-separated)', value=tags_val).props('outlined dense rounded').classes('flex-1')

            with ui.row().classes('w-full gap-3 flex-col sm:flex-row'):
                pub_input = ui.input(label='Publisher', value=str(publisher)).props('outlined dense rounded').classes('flex-1')
                year_input = ui.input(label='Publication Year', value=str(pub_year)).props('outlined dense rounded').classes('flex-1')

            desc_input = ui.textarea(label='Synopsis / Description', value=synopsis_text).props('outlined rounded rows=5').classes('w-full text-sm')

        with ui.row().classes('w-full justify-end gap-2.5 pt-3 border-t border-slate-100'):
            ui.button('Cancel', on_click=edit_dialog.close).props('flat rounded-xl color=grey font-bold size=sm')
            
            async def save_metadata():
                new_title = title_input.value.strip() or title
                new_author = author_input.value.strip() or 'Unknown'
                new_pub = pub_input.value.strip()
                new_year = year_input.value.strip()
                new_desc = book_details_service.format_synopsis_text(desc_input.value.strip())

                clean_shelves = [s.strip() for s in shelves_input.value.split(',') if s.strip()]
                clean_genres = [g.strip() for g in tags_input.value.split(',') if g.strip()]

                updates = {
                    'title': new_title,
                    'display_author': new_author,
                    'authors': [new_author],
                    'publisher': new_pub,
                    'publication_year': new_year,
                    'description': new_desc,
                    'shelves': clean_shelves,
                    'genres': clean_genres,
                }

                success, msg = await book_details_service.update_metadata(book_id, updates)
                if success:
                    edit_dialog.close()
                    ui.notify('Book metadata updated successfully!', type='positive')
                    if on_saved:
                        on_saved(updates)
                else:
                    ui.notify(msg, type='negative')

            ui.button('Save Changes', icon='save', on_click=save_metadata)\
                .props('unelevated rounded-xl color=indigo font-bold size=sm shadow-md')

    edit_dialog.open()


def open_delete_dialog(book_id: str, title: str, on_deleted: Callable[[], None]):
    """Delete Confirmation Dialog (Librarian & Admin Restricted)."""
    if get_current_user_role() not in ('admin', 'librarian'):
        ui.notify("Librarian or Administrator privileges required to delete books.", type='warning')
        return

    with ui.dialog() as del_dialog, ui.card().classes('p-5 sm:p-6 bg-white rounded-3xl max-w-md w-full shadow-2xl border border-slate-200'):
        with ui.row().classes('items-center gap-3 text-red-600 mb-2'):
            with ui.element('div').classes('p-2.5 rounded-2xl bg-red-50 text-red-600 border border-red-100'):
                ui.icon('warning', size='24px')
            ui.label('Delete Document').classes('text-lg font-black text-slate-900')
        
        ui.label(
            f"Are you sure you want to permanently remove '{title}' from your library? "
            "This action cannot be undone."
        ).classes('text-sm text-slate-600 leading-relaxed mb-4')
        
        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Cancel', on_click=del_dialog.close).props('flat rounded-xl color=grey font-bold size=sm')
            
            async def do_delete():
                delete_btn.props('loading')
                success, msg = await book_details_service.delete_book(book_id)
                del_dialog.close()
                if success:
                    ui.notify(f"'{title}' has been deleted.", type='positive')
                    if on_deleted:
                        on_deleted()
                else:
                    ui.notify(msg, type='negative')
                    delete_btn.props(remove='loading')

            delete_btn = ui.button('Delete Permanently', icon='delete_forever', on_click=do_delete)\
                .props('unelevated rounded-xl color=red font-bold size=sm shadow-md')

    del_dialog.open()
