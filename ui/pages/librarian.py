from nicegui import ui, app
from datetime import datetime
import logging

from components.sidebar import sidebar
from components.header import header
from components.bottom_nav import bottom_nav
from components.chat_floating import FloatingChat
from core.database.mongo_manager import mongo_db
from core.auth.jwt_handler import get_current_user_role

logger = logging.getLogger("LIBRARIAN_UI")


async def librarian_dashboard():
    """Librarian Operations & Circulation Console."""
    app.storage.client['page_path'] = '/librarian'
    user_role = get_current_user_role()
    if user_role not in ['admin', 'librarian']:
        ui.notify('Librarian or Administrator privileges required.', type='warning')
        ui.navigate.to('/')
        return

    drawer = sidebar()
    header(drawer_reference=drawer)
    bottom_nav()
    FloatingChat()

    # Load live operational metrics in parallel
    format_counts = await mongo_db.get_catalog_format_counts()
    req_counts = await mongo_db.get_requisition_status_counts()
    pending_reqs = await mongo_db.get_requisitions(status='Pending Review', limit=4)
    active_visitors = await mongo_db.get_active_checked_in_count()
    today_logs = await mongo_db.get_today_attendance_logs(limit=100)
    recent_books = await mongo_db.books.get_recent_books(limit=4)

    total_books = format_counts.get('total', 0)
    epub_count = format_counts.get('epub', 0)
    pdf_count = format_counts.get('pdf', 0)
    pending_count = req_counts.get('Pending Review', 0)

    with ui.column().classes(
        'w-full min-h-[100dvh] pt-[calc(4.5rem+env(safe-area-inset-top,0px))] '
        'px-3 sm:px-6 md:pt-24 md:px-10 max-w-[1600px] mx-auto pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] md:pb-16'
    ):
        # 1. Page Title Banner
        with ui.row().classes('w-full items-start justify-between gap-4 mb-6 flex-wrap'):
            with ui.column().classes('gap-1'):
                with ui.row().classes('items-center gap-2.5'):
                    with ui.element('div').classes('p-2.5 rounded-2xl bg-indigo-50 text-indigo-600 border border-indigo-100 shadow-sm'):
                        ui.icon('local_library', size='28px')
                    with ui.column().classes('gap-0'):
                        ui.label('Librarian Operations Console').classes('text-2xl sm:text-3xl font-black text-slate-900 tracking-tight')
                        ui.label('Collection curation, curricular requisitions (FM-LIBS-002), and circulation terminal (NEMSU Tandag Campus)').classes('text-xs sm:text-sm text-slate-500')
            with ui.row().classes('items-center gap-2'):
                ui.element('span').classes('text-xs font-black uppercase tracking-wider bg-purple-50 text-purple-700 px-3 py-1 rounded-full border border-purple-200') \
                    .text = '📚 Operations Lead'
                if user_role == 'admin':
                    ui.button('Go to Admin IT Console', icon='shield', on_click=lambda: ui.navigate.to('/admin')) \
                        .props('flat rounded-xl color=indigo size=sm font-bold border border-indigo-200 bg-white')

        # 2. Real-time Circulation & Operational Metrics
        with ui.grid().classes('w-full grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 mb-6'):
            metric_cards = [
                ("menu_book", "Catalog Collection", f"{total_books} Books", f"{epub_count} EPUB • {pdf_count} PDF", "text-indigo-600", "bg-indigo-50"),
                ("pending_actions", "Pending Requisitions", f"{pending_count} Requests", "FM-LIBS-002 Curriculum", "text-amber-600", "bg-amber-50"),
                ("sensor_door", "Currently Inside", f"{active_visitors} Visitors", "Active in Reading Room", "text-emerald-600", "bg-emerald-50"),
                ("how_to_reg", "Visitors Today", f"{len(today_logs)} Check-Ins", "FM-LIBS-009 Gate Log", "text-blue-600", "bg-blue-50"),
            ]
            for icon_name, label_text, val_text, sub_text, text_col, bg_col in metric_cards:
                with ui.card().classes('p-3.5 sm:p-5 rounded-2xl bg-white border border-slate-200 shadow-sm'):
                    with ui.row().classes('items-center gap-2 mb-1.5'):
                        with ui.element('div').classes(f'p-1.5 rounded-xl {bg_col} {text_col}'):
                            ui.icon(icon_name, size='18px')
                        ui.label(label_text).classes('text-[11px] font-bold text-slate-400 uppercase tracking-wider truncate')
                    ui.label(val_text).classes('text-xl sm:text-2xl font-black text-slate-900')
                    ui.label(sub_text).classes('text-[10px] sm:text-[11px] text-slate-500 font-medium')

        # 3. Fast Action Command Center
        with ui.card().classes('w-full p-4 sm:p-6 rounded-2xl sm:rounded-3xl bg-white border border-slate-200 shadow-sm mb-6'):
            with ui.row().classes('items-center gap-2 mb-3'):
                ui.icon('bolt', size='sm').classes('text-indigo-600')
                ui.label('QUICK OPERATIONAL ACTIONS').classes('text-xs sm:text-sm font-black text-slate-900 uppercase tracking-widest')

            with ui.grid().classes('w-full grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3'):
                actions = [
                    ('cloud_upload', 'Ingest & Catalog Book', 'Upload EPUB or PDF documents with AI auto-metadata.', '/upload', 'text-indigo-600', 'hover:border-indigo-300'),
                    ('post_add', 'Faculty Requisitions', f'{pending_count} pending textbook procurement requests.', '/requisitions', 'text-amber-600', 'hover:border-amber-300'),
                    ('qr_code_scanner', 'Attendance Terminal', 'Scan student QR passes or input barcodes at the gate.', '/attendance', 'text-emerald-600', 'hover:border-emerald-300'),
                    ('insights', 'Program Analytics', 'Inspect department utilization and borrowing trends.', '/analytics', 'text-purple-600', 'hover:border-purple-300'),
                ]
                for act_icon, act_title, act_desc, act_route, act_color, act_border in actions:
                    with ui.card().classes(f'p-4 rounded-2xl border border-slate-200 bg-slate-50/70 hover:bg-white {act_border} cursor-pointer transition-all shadow-xs') \
                            .on('click', lambda r=act_route: ui.navigate.to(r)):
                        with ui.row().classes('items-center gap-2 mb-1.5'):
                            ui.icon(act_icon, size='20px').classes(act_color)
                            ui.label(act_title).classes('text-sm font-bold text-slate-900')
                        ui.label(act_desc).classes('text-[11px] text-slate-500 leading-snug')

        # 4. Two-Column Dashboard Layout
        with ui.grid().classes('w-full grid-cols-1 lg:grid-cols-12 gap-6'):

            # Left Column (7 cols): Requisitions Spotlight & Recent Ingestion
            with ui.column().classes('lg:col-span-7 gap-6'):

                # Section A: Curricular Requisitions Spotlight (FM-LIBS-002)
                with ui.card().classes('w-full p-4 sm:p-6 rounded-2xl sm:rounded-3xl bg-white border border-slate-200 shadow-sm'):
                    with ui.row().classes('w-full items-center justify-between gap-2 mb-4'):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('assignment_late', size='sm').classes('text-amber-600')
                            ui.label('Faculty Requisition Queue').classes('text-sm sm:text-base font-black text-slate-900')
                            ui.element('span').classes('text-[10px] font-bold bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded border border-indigo-200').text = 'FM-LIBS-002'
                        ui.button('View All Requests', icon='arrow_forward', on_click=lambda: ui.navigate.to('/requisitions')) \
                            .props('flat rounded-xl color=indigo size=xs font-bold')

                    if not pending_reqs:
                        with ui.element('div').classes('w-full p-6 bg-slate-50 rounded-2xl text-center border border-slate-100'):
                            ui.icon('task_alt', size='32px').classes('text-emerald-500 mb-1')
                            ui.label('All faculty requisitions have been processed!').classes('text-xs font-bold text-slate-700')
                            ui.label('No pending requests awaiting librarian committee review.').classes('text-[11px] text-slate-400')
                    else:
                        with ui.column().classes('w-full gap-2.5'):
                            for r in pending_reqs:
                                with ui.card().classes('w-full p-3.5 rounded-2xl border border-slate-100 bg-slate-50/60 hover:bg-slate-50 hover:border-slate-200 transition-all shadow-xs'):
                                    with ui.row().classes('w-full items-start justify-between gap-2'):
                                        with ui.column().classes('gap-0.5 min-w-0 flex-1'):
                                            ui.label(r.get('book_title', 'Untitled')).classes('text-sm font-black text-slate-900 truncate')
                                            with ui.row().classes('items-center gap-1.5 flex-wrap text-[11px] text-slate-500'):
                                                ui.label(f"By {r.get('author', 'Unknown Author')}")
                                                ui.label('•')
                                                ui.label(f"Course: {r.get('course_code', 'N/A')}").classes('font-bold text-indigo-600')
                                                ui.label('•')
                                                ui.label(f"Faculty: {r.get('faculty_name', 'Faculty')}")
                                        ui.button('Review', icon='open_in_new', on_click=lambda: ui.navigate.to('/requisitions')) \
                                            .props('unelevated rounded-xl color=indigo size=xs font-bold')

                # Section B: Recently Ingested Titles
                with ui.card().classes('w-full p-4 sm:p-6 rounded-2xl sm:rounded-3xl bg-white border border-slate-200 shadow-sm'):
                    with ui.row().classes('w-full items-center justify-between gap-2 mb-4'):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('auto_stories', size='sm').classes('text-indigo-600')
                            ui.label('Recently Cataloged Titles').classes('text-sm sm:text-base font-black text-slate-900')
                        ui.button('Open Archive', icon='collections_bookmark', on_click=lambda: ui.navigate.to('/books')) \
                            .props('flat rounded-xl color=indigo size=xs font-bold')

                    with ui.column().classes('w-full gap-2.5'):
                        for b in recent_books:
                            b_id = b.get('id')
                            ft = str(b.get('file_type', 'epub')).upper()
                            with ui.row().classes('w-full p-2.5 rounded-2xl border border-slate-100 bg-slate-50/60 items-center justify-between gap-3 hover:bg-slate-50 transition-all'):
                                with ui.row().classes('items-center gap-2.5 min-w-0 flex-1'):
                                    ui.avatar(icon='menu_book', color='indigo-50', text_color='indigo-600', size='34px') \
                                        .classes('border border-indigo-100 shrink-0 font-bold')
                                    with ui.column().classes('gap-0 min-w-0 flex-1'):
                                        ui.label(b.get('title', 'Untitled')).classes('text-xs sm:text-sm font-bold text-slate-900 truncate')
                                        ui.label(b.get('display_author', 'Unknown Author')).classes('text-[11px] text-slate-400 truncate')
                                with ui.row().classes('items-center gap-2 shrink-0'):
                                    ui.element('span').classes('text-[10px] font-black uppercase px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200') \
                                        .text = ft
                                    ui.button(icon='arrow_forward', on_click=lambda bid=b_id: ui.navigate.to(f'/book/{bid}')) \
                                        .props('flat round dense size=sm color=indigo')

            # Right Column (5 cols): OPDS Feed, Format Ratio, Entrance Summary
            with ui.column().classes('lg:col-span-5 gap-6'):

                # Section C: OPDS E-Reader Feed Hub
                with ui.card().classes('w-full p-4 sm:p-6 rounded-2xl sm:rounded-3xl bg-white border border-slate-200 shadow-sm'):
                    with ui.row().classes('items-center gap-2 mb-1.5'):
                        ui.icon('wifi_tethering', size='sm').classes('text-indigo-600')
                        ui.label('OPDS E-READER FEED').classes('text-sm font-black text-slate-900')
                    ui.label('Broadcast your institutional catalog over Wi-Fi directly to dedicated e-readers and mobile reading apps.').classes('text-xs text-slate-500 mb-3 leading-snug')

                    with ui.column().classes('w-full p-3 bg-slate-50 rounded-2xl border border-slate-200 gap-2 mb-3'):
                        opds_lbl = ui.label("http://<host>:8080/opds").classes('font-mono text-xs font-bold text-slate-800 break-all')
                        ui.run_javascript(f'const el = document.getElementById("{opds_lbl.id}"); if(el) el.innerText = window.location.origin + "/opds";')
                        ui.button('Copy OPDS Feed URL', icon='content_copy', on_click=lambda: ui.run_javascript("""
                            navigator.clipboard.writeText(window.location.origin + '/opds');
                            alert('OPDS Feed URL copied! Enter this URL in your e-reader app.');
                        """)).props('unelevated rounded-xl color=indigo size=xs font-bold w-full')

                    with ui.column().classes('w-full gap-1 text-[11px] text-slate-500'):
                        ui.label('📱 Compatible with: Apple Books, Moon+ Reader, KOReader (Kindle/Kobo), Foliate, and Thorium Reader.').classes('italic')

                # Section D: Collection Format Distribution
                with ui.card().classes('w-full p-4 sm:p-6 rounded-2xl sm:rounded-3xl bg-white border border-slate-200 shadow-sm'):
                    with ui.row().classes('items-center gap-2 mb-3'):
                        ui.icon('pie_chart', size='sm').classes('text-indigo-600')
                        ui.label('COLLECTION FORMATS').classes('text-xs sm:text-sm font-black text-slate-900 uppercase tracking-wider')

                    epub_pct = round((epub_count / max(total_books, 1)) * 100)
                    pdf_pct = round((pdf_count / max(total_books, 1)) * 100)

                    with ui.column().classes('w-full gap-3'):
                        # EPUB Bar
                        with ui.column().classes('w-full gap-1'):
                            with ui.row().classes('w-full items-center justify-between text-xs font-bold text-slate-700'):
                                ui.label('EPUB (Reflowable Dynamic Layout)')
                                ui.label(f"{epub_count} ({epub_pct}%)")
                            with ui.element('div').classes('w-full h-2 rounded-full bg-slate-100 overflow-hidden'):
                                ui.element('div').classes('h-full bg-indigo-600 rounded-full').style(f'width: {epub_pct}%;')

                        # PDF Bar
                        with ui.column().classes('w-full gap-1'):
                            with ui.row().classes('w-full items-center justify-between text-xs font-bold text-slate-700'):
                                ui.label('PDF (Fixed Document Page Layout)')
                                ui.label(f"{pdf_count} ({pdf_pct}%)")
                            with ui.element('div').classes('w-full h-2 rounded-full bg-slate-100 overflow-hidden'):
                                ui.element('div').classes('h-full bg-emerald-500 rounded-full').style(f'width: {pdf_pct}%;')

                # Section E: Entrance Attendance Overview (FM-LIBS-009)
                with ui.card().classes('w-full p-4 sm:p-6 rounded-2xl sm:rounded-3xl bg-white border border-slate-200 shadow-sm'):
                    with ui.row().classes('w-full items-center justify-between gap-2 mb-2'):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('door_front', size='sm').classes('text-emerald-600')
                            ui.label('Entrance Doorway Summary').classes('text-sm font-black text-slate-900')
                        ui.element('span').classes('text-[10px] font-bold bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded border border-indigo-200').text = 'FM-LIBS-009'

                    ui.label('Student QR check-ins actively recorded at the library main entrance door today.').classes('text-xs text-slate-500 mb-3')
                    
                    with ui.row().classes('w-full p-3 bg-slate-50 rounded-2xl border border-slate-100 items-center justify-between mb-3'):
                        with ui.column().classes('gap-0'):
                            ui.label('Active in Library').classes('text-[11px] font-bold text-slate-400 uppercase tracking-wider')
                            ui.label(f"{active_visitors} Visitors").classes('text-lg font-black text-slate-900')
                        ui.button('Open Gate Terminal', icon='qr_code_scanner', on_click=lambda: ui.navigate.to('/attendance')) \
                            .props('unelevated rounded-xl color=emerald size=xs font-bold')
