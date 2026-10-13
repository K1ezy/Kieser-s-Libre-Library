from nicegui import ui, app
from core.database.mongo_manager import mongo_db
from core.utils.media_handler import save_user_media
from components.sidebar import sidebar
from components.header import header
from ui.pages.attendance import generate_qr_base64
import asyncio
from typing import Optional, Dict, Any

PROGRAM_OPTIONS = ["BSCS", "BSIT", "BSED", "BEED", "BSBA", "BSHM", "Crim", "Nursing", "GENERAL"]
YEAR_LEVEL_OPTIONS = ["1st Year", "2nd Year", "3rd Year", "4th Year", "Graduate"]

ROLE_CONFIGS = {
    "STUDENT": {
        "title": "STUDENT",
        "badge_color": "emerald",
        "badge_bg": "bg-emerald-50 text-emerald-700 border-emerald-200",
        "card_gradient": "from-emerald-700 via-teal-800 to-slate-900",
        "accent_hex": "#10b981",
        "icon": "school",
        "id_name": "Student ID Number",
        "unit_name": "Academic Program",
    },
    "FACULTY": {
        "title": "FACULTY",
        "badge_color": "blue",
        "badge_bg": "bg-blue-50 text-blue-700 border-blue-200",
        "card_gradient": "from-blue-700 via-indigo-800 to-slate-900",
        "accent_hex": "#3b82f6",
        "icon": "cast_for_education",
        "id_name": "Faculty / Employee ID",
        "unit_name": "Department",
    },
    "LIBRARIAN": {
        "title": "LIBRARIAN",
        "badge_color": "purple",
        "badge_bg": "bg-purple-50 text-purple-700 border-purple-200",
        "card_gradient": "from-purple-700 via-indigo-900 to-slate-900",
        "accent_hex": "#a855f7",
        "icon": "local_library",
        "id_name": "Staff ID Number",
        "unit_name": "Library Branch / Section",
    },
    "ADMIN": {
        "title": "ADMINISTRATOR",
        "badge_color": "amber",
        "badge_bg": "bg-amber-50 text-amber-800 border-amber-200",
        "card_gradient": "from-amber-600 via-slate-800 to-slate-950",
        "accent_hex": "#f59e0b",
        "icon": "admin_panel_settings",
        "id_name": "Admin ID / Employee Code",
        "unit_name": "Governance Unit",
    },
}

def get_user_initials(name: str = "", username: str = "") -> str:
    """Generates two-letter uppercase fallback initials."""
    raw = (name or username or "U").strip()
    parts = [p for p in raw.split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    elif parts and len(parts[0]) >= 2:
        return parts[0][:2].upper()
    elif parts:
        return parts[0][0].upper()
    return "LU"


class UserProfile:
    def __init__(self):
        self.profile_data: Dict[str, Any] = {}
        self.stats: Dict[str, Any] = {}
        self.is_editing: bool = False

        # Input handles for editing
        self.name_input = None
        self.headline_input = None
        self.bio_input = None
        self.id_input = None
        self.program_input = None
        self.year_input = None
        self.dept_input = None
        self.branch_input = None

    async def load_data(self):
        """Loads profile and stats strictly isolated to the current user."""
        user_id = app.storage.user.get('user_id')
        self.profile_data = await mongo_db.get_user_profile(user_id=user_id)
        self.stats = await mongo_db.get_library_stats(user_id=user_id)
        self.render_content.refresh()

    async def save_changes(self):
        """Persists profile and institutional ID metadata changes."""
        user_id = app.storage.user.get('user_id') or self.profile_data.get('id')
        if not user_id:
            ui.notify('Session expired. Please log in again.', type='negative')
            return ui.navigate.to('/login')

        name_val = self.name_input.value if self.name_input else self.profile_data.get('name')
        bio_val = self.bio_input.value if self.bio_input else self.profile_data.get('bio')
        head_val = self.headline_input.value if self.headline_input else self.profile_data.get('headline')
        id_val = self.id_input.value if self.id_input else (
            self.profile_data.get('institutional_id') or self.profile_data.get('student_id')
        )
        prog_val = self.program_input.value if self.program_input else self.profile_data.get('program')
        year_val = self.year_input.value if self.year_input else self.profile_data.get('year_level')
        dept_val = self.dept_input.value if self.dept_input else self.profile_data.get('department')
        branch_val = self.branch_input.value if self.branch_input else self.profile_data.get('branch')

        await mongo_db.update_user_profile(
            user_id=user_id,
            name=name_val,
            bio=bio_val,
            headline=head_val,
            institutional_id=id_val,
            student_id=id_val,
            program=prog_val,
            year_level=year_val,
            department=dept_val,
            branch=branch_val
        )
        self.is_editing = False
        ui.notify('Profile & Institutional Credentials updated successfully!', type='positive')
        await self.load_data()

    def toggle_edit(self):
        self.is_editing = not self.is_editing
        self.render_content.refresh()

    def open_avatar_modal(self):
        """Interactive modal for uploading/previewing circular avatar with 2MB validation."""
        user_id = app.storage.user.get('user_id') or self.profile_data.get('id')
        with ui.dialog() as avatar_dialog, ui.card().classes(
            'w-[calc(100vw-2rem)] max-w-md p-5 rounded-3xl bg-white border border-slate-200 shadow-2xl'
        ):
            with ui.row().classes('w-full justify-between items-center mb-2'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('photo_camera', size='sm').classes('text-indigo-600')
                    ui.label('Update Profile Photo').classes('text-base font-bold text-slate-800')
                ui.button(icon='close', on_click=avatar_dialog.close).props('flat round dense size=sm color=grey')

            ui.label('Upload a square photo in JPEG, PNG, or WebP format (Max 2MB).').classes('text-xs text-slate-500 mb-4')

            with ui.row().classes('w-full justify-center mb-4'):
                current_avatar = self.profile_data.get('avatar_url')
                if current_avatar:
                    ui.image(current_avatar).classes('w-24 h-24 rounded-full object-cover border-2 border-indigo-200 shadow-sm')
                else:
                    initials = get_user_initials(self.profile_data.get('name'), self.profile_data.get('username'))
                    with ui.element('div').classes('w-24 h-24 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-black text-2xl shadow-sm'):
                        ui.label(initials)

            async def handle_avatar_upload(e):
                try:
                    c = e.content
                    raw_bytes = await c.read() if asyncio.iscoroutinefunction(getattr(c, 'read', None)) else c.read()
                    success, msg, url = save_user_media(user_id, raw_bytes, e.name, "avatar")
                    if not success:
                        ui.notify(msg, type='negative')
                        return
                    await mongo_db.update_user_media(user_id, avatar_url=url)
                    self.profile_data['avatar_url'] = url
                    app.storage.user['avatar_url'] = url
                    ui.notify('Avatar updated successfully!', type='positive')
                    avatar_dialog.close()
                    self.render_content.refresh()
                except Exception as err:
                    ui.notify(f'Upload failed: {err}', type='negative')

            ui.upload(
                label="Select or drop photo here",
                auto_upload=True,
                on_upload=handle_avatar_upload,
                max_file_size=2_097_152
            ).props('accept=".jpg,.jpeg,.png,.webp" flat bordered color=indigo').classes('w-full rounded-2xl')

            with ui.row().classes('w-full justify-end mt-4'):
                ui.button('Cancel', on_click=avatar_dialog.close).props('flat rounded-xl color=grey size=sm font-bold')
        avatar_dialog.open()

    def open_cover_modal(self):
        """Interactive modal for uploading/previewing cover banner with 5MB validation."""
        user_id = app.storage.user.get('user_id') or self.profile_data.get('id')
        with ui.dialog() as cover_dialog, ui.card().classes(
            'w-[calc(100vw-2rem)] max-w-lg p-5 rounded-3xl bg-white border border-slate-200 shadow-2xl'
        ):
            with ui.row().classes('w-full justify-between items-center mb-2'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('image', size='sm').classes('text-indigo-600')
                    ui.label('Update Cover Photo').classes('text-base font-bold text-slate-800')
                ui.button(icon='close', on_click=cover_dialog.close).props('flat round dense size=sm color=grey')

            ui.label('Upload a banner image in JPEG, PNG, or WebP format (Max 5MB, ~3:1 ratio recommended).').classes('text-xs text-slate-500 mb-4')

            with ui.row().classes('w-full justify-center mb-4'):
                current_cover = self.profile_data.get('cover_url')
                if current_cover:
                    ui.image(current_cover).classes('w-full h-28 rounded-xl object-cover border border-slate-200 shadow-sm')
                else:
                    with ui.element('div').classes('w-full h-28 rounded-xl bg-gradient-to-r from-indigo-700 via-purple-700 to-slate-900 flex items-center justify-center text-white/80 text-xs font-bold'):
                        ui.label('Default Gradient Banner Active')

            async def handle_cover_upload(e):
                try:
                    c = e.content
                    raw_bytes = await c.read() if asyncio.iscoroutinefunction(getattr(c, 'read', None)) else c.read()
                    success, msg, url = save_user_media(user_id, raw_bytes, e.name, "cover")
                    if not success:
                        ui.notify(msg, type='negative')
                        return
                    await mongo_db.update_user_media(user_id, cover_url=url)
                    self.profile_data['cover_url'] = url
                    app.storage.user['cover_url'] = url
                    ui.notify('Cover photo updated successfully!', type='positive')
                    cover_dialog.close()
                    self.render_content.refresh()
                except Exception as err:
                    ui.notify(f'Upload failed: {err}', type='negative')

            ui.upload(
                label="Select or drop cover banner here",
                auto_upload=True,
                on_upload=handle_cover_upload,
                max_file_size=5_242_880
            ).props('accept=".jpg,.jpeg,.png,.webp" flat bordered color=indigo').classes('w-full rounded-2xl')

            with ui.row().classes('w-full justify-end mt-4'):
                ui.button('Cancel', on_click=cover_dialog.close).props('flat rounded-xl color=grey size=sm font-bold')
        cover_dialog.open()

    @ui.refreshable
    def render_content(self):
        # 1. Resolve User & Role Metadata
        raw_role = str(self.profile_data.get('role', 'student')).upper()
        norm_role = 'STUDENT' if raw_role in ('USER', 'STUDENT') else raw_role
        role_cfg = ROLE_CONFIGS.get(norm_role, ROLE_CONFIGS['STUDENT'])

        user_name = self.profile_data.get('name') or self.profile_data.get('username') or 'Library Member'
        username = self.profile_data.get('username') or 'user'
        email = self.profile_data.get('email') or 'N/A'
        inst_id = self.profile_data.get('institutional_id') or self.profile_data.get('student_id') or '2024-001'
        program = self.profile_data.get('program') or 'BSCS'
        year_level = self.profile_data.get('year_level') or '1st Year'
        dept = self.profile_data.get('department') or 'College of Computing'
        branch = self.profile_data.get('branch') or 'Main Library Archive'
        admin_code = self.profile_data.get('admin_code') or inst_id
        avatar_url = self.profile_data.get('avatar_url')
        cover_url = self.profile_data.get('cover_url')
        initials = get_user_initials(user_name, username)

        # -------------------------------------------------------------
        # 2. ASPECT RATIO COVER PHOTO BANNER WITH OVERLAY BUTTON
        # -------------------------------------------------------------
        with ui.element('div').classes('w-full h-40 sm:h-56 md:h-64 rounded-2xl sm:rounded-3xl relative overflow-hidden shadow-md border border-slate-200/90'):
            if cover_url:
                ui.image(cover_url).classes('w-full h-full object-cover')
            else:
                with ui.element('div').classes(
                    'w-full h-full bg-gradient-to-r from-indigo-800 via-purple-800 to-slate-900 flex items-center justify-end p-6'
                ):
                    ui.icon('auto_stories', size='5rem').classes('text-white/10')

            # "Edit Cover" Overlay Action Button
            with ui.row().classes('absolute top-3 right-3 sm:top-4 sm:right-4 z-10'):
                ui.button('Edit Cover', icon='photo_camera', on_click=self.open_cover_modal).props(
                    'unelevated rounded-xl size=sm'
                ).classes(
                    'bg-slate-900/60 hover:bg-slate-900/80 text-white backdrop-blur-md border border-white/20 text-xs font-bold shadow-md transition-all'
                )

        # -------------------------------------------------------------
        # 3. AVATAR & MAIN USER PROFILE CARD
        # -------------------------------------------------------------
        with ui.column().classes('w-full max-w-5xl mx-auto -mt-16 sm:-mt-20 px-1 sm:px-4'):
            with ui.card().classes('w-full p-4 sm:p-6 md:p-8 rounded-2xl sm:rounded-3xl shadow-xl bg-white border border-slate-200'):
                with ui.row().classes('w-full items-center sm:items-end gap-4 sm:gap-6 flex-col sm:flex-row text-center sm:text-left'):

                    # Circular Avatar with Fallback Initials & Upload Icon Overlay
                    with ui.element('div').classes('relative w-24 h-24 sm:w-32 sm:h-32 rounded-full border-4 border-white shadow-xl overflow-hidden bg-slate-100 shrink-0 group'):
                        if avatar_url:
                            ui.image(avatar_url).classes('w-full h-full object-cover')
                        else:
                            with ui.element('div').classes(
                                'w-full h-full flex items-center justify-center bg-gradient-to-br from-indigo-500 via-indigo-600 to-purple-600 text-white font-black text-2xl sm:text-3xl select-none'
                            ):
                                ui.label(initials)

                        # Floating Avatar Camera Icon Button
                        ui.button(icon='photo_camera', on_click=self.open_avatar_modal).props(
                            'flat round dense size=sm'
                        ).classes(
                            'absolute bottom-1 right-1 bg-indigo-600 hover:bg-indigo-700 text-white border-2 border-white shadow-md transition-all'
                        ).tooltip('Upload Avatar Photo')

                    # Profile Core Metadata
                    with ui.column().classes('mb-1 sm:mb-2 flex-grow min-w-0 w-full sm:w-auto items-center sm:items-start'):
                        if not self.is_editing:
                            with ui.row().classes('items-center gap-2 flex-wrap justify-center sm:justify-start'):
                                ui.label(user_name).classes('text-2xl sm:text-3xl font-black text-slate-900 leading-tight tracking-tight')
                                with ui.element('div').classes(
                                    f'text-[10px] font-black px-2.5 py-0.5 rounded-full uppercase tracking-wider border flex items-center gap-1 {role_cfg["badge_bg"]}'
                                ):
                                    ui.icon(role_cfg['icon'], size='14px')
                                    ui.label(norm_role)

                            with ui.row().classes('items-center gap-2 mt-1.5 flex-wrap justify-center sm:justify-start'):
                                with ui.element('span').classes('text-xs font-mono font-bold text-slate-800 bg-slate-100 border border-slate-200 px-2.5 py-0.5 rounded-lg shadow-2xs'):
                                    ui.label(f"{role_cfg['id_name']}: {inst_id}")
                                if norm_role == 'STUDENT':
                                    ui.label(f"{program} • {year_level}").classes('text-xs font-black text-emerald-700 bg-emerald-50 border border-emerald-100 px-2.5 py-0.5 rounded-lg')
                                elif norm_role == 'FACULTY':
                                    ui.label(dept).classes('text-xs font-black text-blue-700 bg-blue-50 border border-blue-100 px-2.5 py-0.5 rounded-lg')
                                elif norm_role == 'LIBRARIAN':
                                    ui.label(branch).classes('text-xs font-black text-purple-700 bg-purple-50 border border-purple-100 px-2.5 py-0.5 rounded-lg')
                                elif norm_role == 'ADMIN':
                                    ui.label("System Governance").classes('text-xs font-black text-amber-700 bg-amber-50 border border-amber-100 px-2.5 py-0.5 rounded-lg')

                                ui.label(self.profile_data.get('headline', 'Academic Scholar & Researcher')).classes('text-xs text-slate-500 font-medium')
                        else:
                            # Dynamic Edit Mode Forms
                            self.name_input = ui.input(value=user_name, label='Full Legal Name').props('outlined dense rounded bg-color=white').classes('w-full text-sm')
                            with ui.row().classes('w-full gap-2.5 flex-wrap sm:flex-nowrap'):
                                self.id_input = ui.input(value=inst_id, label=role_cfg['id_name']).props('outlined dense rounded bg-color=white').classes('flex-1 text-sm')
                                if norm_role == 'STUDENT':
                                    self.program_input = ui.select(PROGRAM_OPTIONS, value=program, label='Program').props('outlined dense rounded bg-color=white options-dense').classes('w-32 text-sm')
                                    self.year_input = ui.select(YEAR_LEVEL_OPTIONS, value=year_level, label='Year Level').props('outlined dense rounded bg-color=white options-dense').classes('w-32 text-sm')
                                elif norm_role == 'FACULTY':
                                    self.dept_input = ui.input(value=dept, label='Department / College').props('outlined dense rounded bg-color=white').classes('flex-1 text-sm')
                                elif norm_role == 'LIBRARIAN':
                                    self.branch_input = ui.input(value=branch, label='Library Branch / Section').props('outlined dense rounded bg-color=white').classes('flex-1 text-sm')
                                elif norm_role == 'ADMIN':
                                    self.branch_input = ui.input(value=admin_code, label='Admin Verification Code').props('outlined dense rounded bg-color=white').classes('flex-1 text-sm')

                            self.headline_input = ui.input(
                                value=self.profile_data.get('headline', 'Academic Scholar & Researcher'),
                                label='Academic Headline / Discipline'
                            ).props('outlined dense rounded bg-color=white').classes('w-full text-sm')

                    # Action Buttons
                    if not self.is_editing:
                        ui.button('Edit Profile', icon='edit', on_click=self.toggle_edit).props(
                            'flat rounded-xl color=indigo font-bold size=sm'
                        ).classes('self-center sm:self-end border border-slate-200 hover:bg-slate-50 shadow-2xs')
                    else:
                        with ui.row().classes('gap-2 self-center sm:self-end mt-2'):
                            ui.button('Cancel', on_click=self.toggle_edit).props('flat rounded-xl color=red size=sm font-bold')
                            ui.button('Save Changes', icon='save', on_click=self.save_changes).props('unelevated rounded-xl color=indigo size=sm font-bold shadow-md')

                ui.separator().classes('my-5 opacity-60')

                # -------------------------------------------------------------
                # 4. INSTITUTIONAL DIGITAL PVC ID BADGE (MULTI-ROLE DISPLAY)
                # -------------------------------------------------------------
                qr_code_b64 = generate_qr_base64(inst_id)

                with ui.element('div').classes(
                    'w-full p-4 sm:p-6 rounded-2xl sm:rounded-3xl bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 '
                    'border border-indigo-500/30 text-white shadow-xl relative overflow-hidden mb-5'
                ):
                    # Background Watermark
                    with ui.element('div').classes('absolute right-[-20px] bottom-[-20px] opacity-10 pointer-events-none'):
                        ui.icon('local_library', size='12rem')

                    # ID Card Header Strip
                    with ui.row().classes('w-full justify-between items-center mb-4 pb-3 border-b border-white/10 gap-2 flex-wrap'):
                        with ui.row().classes('items-center gap-2.5'):
                            with ui.element('div').classes('p-1.5 rounded-lg bg-white/10 border border-white/20 text-white'):
                                ui.icon('local_library', size='18px')
                            with ui.column().classes('gap-0'):
                                ui.label('LIBRE ACADEMIC ECOSYSTEM').classes('text-[10px] font-black tracking-widest text-indigo-300 uppercase')
                                ui.label('OFFICIAL INSTITUTIONAL SMART PASS').classes('text-xs font-bold text-white')

                        with ui.row().classes('items-center gap-2'):
                            with ui.row().classes('items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/20 border border-emerald-400/30 text-emerald-300 text-[10px] font-black uppercase tracking-wider'):
                                ui.element('div').classes('w-2 h-2 rounded-full bg-emerald-400 animate-pulse')
                                ui.label('ACTIVE • VERIFIED')
                            ui.icon('contactless', size='20px').classes('text-indigo-300')

                    # ID Card Body
                    with ui.row().classes('w-full items-center justify-between gap-4 flex-col md:flex-row'):
                        # Left: Photo + Name + Institutional Role
                        with ui.row().classes('items-center gap-4 flex-1 min-w-0 w-full md:w-auto'):
                            # Embedded Small Photo
                            with ui.element('div').classes('w-16 h-16 sm:w-20 sm:h-20 rounded-2xl border-2 border-indigo-400/50 overflow-hidden bg-slate-800 shrink-0 shadow-md'):
                                if avatar_url:
                                    ui.image(avatar_url).classes('w-full h-full object-cover')
                                else:
                                    with ui.element('div').classes('w-full h-full flex items-center justify-center bg-indigo-700 text-white font-black text-xl'):
                                        ui.label(initials)

                            with ui.column().classes('gap-1 min-w-0 flex-1'):
                                ui.label(user_name).classes('text-lg sm:text-xl font-black text-white truncate w-full')
                                with ui.row().classes('items-center gap-2 flex-wrap'):
                                    with ui.element('div').classes(f'text-[9px] font-black px-2 py-0.5 rounded-md uppercase tracking-wider {role_cfg["badge_bg"]}'):
                                        ui.label(norm_role)
                                    ui.label(f"ID: {inst_id}").classes('text-xs font-mono font-bold text-indigo-200 bg-white/10 px-2 py-0.5 rounded-md')

                                if norm_role == 'STUDENT':
                                    ui.label(f"Program: {program} ({year_level})").classes('text-xs text-slate-300 font-medium')
                                elif norm_role == 'FACULTY':
                                    ui.label(f"Department: {dept}").classes('text-xs text-slate-300 font-medium')
                                elif norm_role == 'LIBRARIAN':
                                    ui.label(f"Branch: {branch}").classes('text-xs text-slate-300 font-medium')
                                elif norm_role == 'ADMIN':
                                    ui.label(f"Access Code: {admin_code}").classes('text-xs text-slate-300 font-medium')

                        # Right: High-Contrast Scan QR Code + Quick Open Button
                        with ui.row().classes('items-center gap-3 shrink-0 self-center md:self-auto'):
                            with ui.element('div').classes('p-2 bg-white rounded-xl shadow-md border border-white/20 shrink-0'):
                                ui.image(qr_code_b64).classes('w-16 h-16 sm:w-20 sm:h-20 rounded-lg')
                            with ui.column().classes('gap-1'):
                                ui.label('DOOR ACCESS').classes('text-[9px] font-black text-indigo-300 uppercase tracking-widest')
                                ui.button('Attendance Pass', icon='qr_code_scanner', on_click=lambda: ui.navigate.to('/attendance')).props(
                                    'unelevated rounded-xl color=indigo size=sm font-bold'
                                ).classes('shadow-md text-xs')

                # -------------------------------------------------------------
                # 5. BIOGRAPHY SECTION
                # -------------------------------------------------------------
                ui.label('BIOGRAPHY & RESEARCH INTERESTS').classes('text-[11px] sm:text-xs font-bold text-slate-400 uppercase tracking-widest mb-1.5')
                if not self.is_editing:
                    ui.label(
                        self.profile_data.get('bio', 'Dedicated learner and researcher utilizing Libre-Library.')
                    ).classes('text-slate-700 leading-relaxed text-sm sm:text-base break-words')
                else:
                    self.bio_input = ui.textarea(
                        value=self.profile_data.get('bio', ''),
                        label='Personal Bio / Research Goals'
                    ).props('outlined rounded bg-color=white').classes('w-full text-sm')

                ui.separator().classes('my-5 opacity-60')

                # -------------------------------------------------------------
                # 6. ACTIVITY & SUBSYSTEM STATS
                # -------------------------------------------------------------
                ui.label('ACTIVITY STATS & READERSHIP').classes('text-[11px] sm:text-xs font-bold text-slate-400 uppercase tracking-widest mb-3')
                with ui.grid().classes('grid-cols-2 md:grid-cols-4 gap-3 w-full'):
                    def stat_badge(label, value, icon, color):
                        with ui.column().classes(f'p-3.5 sm:p-4 rounded-2xl bg-{color}-50 border border-{color}-200/80 items-center justify-center text-center shadow-2xs'):
                            ui.icon(icon, size='sm').classes(f'text-{color}-600 mb-1')
                            ui.label(str(value)).classes(f'text-xl sm:text-2xl font-bold text-{color}-700 leading-none')
                            ui.label(label).classes(f'text-[9px] sm:text-[10px] font-bold text-{color}-600 uppercase tracking-wider mt-1')

                    stat_badge('Tasks Done', self.stats.get('tasks_done', 0), 'check_circle', 'emerald')
                    stat_badge('Books Read', self.stats.get('books', 0), 'library_books', 'indigo')
                    stat_badge('System Status', 'Online', 'wifi', 'sky')
                    stat_badge('TARS AI Assistant', 'Active', 'smart_toy', 'purple')

    def build_ui(self):
        """Constructs the authoritative page layout with slide-over drawer navigation."""
        drawer = sidebar()
        header(drawer_reference=drawer)
        
        with ui.column().classes(
            'w-full min-h-fit pt-[calc(4.5rem+env(safe-area-inset-top,0px))] md:pt-24 px-3 sm:px-6 md:px-8 max-w-5xl mx-auto pb-16'
        ):
            self.render_content()


async def profile_page():
    app.storage.client['page_path'] = '/profile'
    page = UserProfile()
    page.build_ui()
    await page.load_data()