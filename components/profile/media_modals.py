from typing import Callable, Any, Optional
from nicegui import ui
from core.database.mongo_manager import mongo_db
from core.utils.media_handler import save_user_media, extract_upload_file

MEDIA_UPLOAD_CSS = """
/* Modern Tailwind dropzone for Quasar q-uploader */
.libre-dropzone.q-uploader {
    width: 100% !important;
    max-height: none !important;
    background: #F8FAFC !important;
    border: 2px dashed #CBD5E1 !important;
    border-radius: 0.75rem !important;
    box-shadow: none !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}
.libre-dropzone.q-uploader:hover {
    border-color: #4F46E5 !important;
    background: #EEF2FF !important;
}
.libre-dropzone .q-uploader__header {
    background: transparent !important;
    color: #1E293B !important;
    padding: 1.25rem 1rem !important;
}
.libre-dropzone .q-uploader__header-content {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    text-align: center !important;
    gap: 0.35rem !important;
}
.libre-dropzone .q-uploader__title {
    font-size: 0.875rem !important;
    font-weight: 600 !important;
    color: #334155 !important;
}
/* Hide the raw "0.0B / 0.00%" counter and empty white list box */
.libre-dropzone .q-uploader__subtitle,
.libre-dropzone .q-uploader__list {
    display: none !important;
}
/* Enhance file trigger button for Fitts's Law touch target */
.libre-dropzone .q-uploader__header .q-btn {
    background: #EEF2FF !important;
    color: #4F46E5 !important;
    border-radius: 9999px !important;
    padding: 0.35rem !important;
}
"""


def _open_media_upload_modal(
    mode: str,
    user_id: str,
    current_media: Optional[str],
    initials: str,
    on_uploaded: Callable[[str], Any]
) -> None:
    """DRY reusable media modal for profile avatar and cover photo uploads."""
    ui.add_css(MEDIA_UPLOAD_CSS)
    is_avatar = mode == 'avatar'
    title = 'Update Profile Photo' if is_avatar else 'Update Cover Photo'
    icon_name = 'photo_camera' if is_avatar else 'wallpaper'
    helper_text = (
        'Upload a square photo in JPEG, PNG, or WebP format (Max 2MB).'
        if is_avatar
        else 'Upload a banner image in JPEG, PNG, or WebP format (Max 5MB, ~3:1 ratio recommended).'
    )
    max_bytes = 2 * 1024 * 1024 if is_avatar else 5 * 1024 * 1024

    staged = {
        'url': current_media,
        'raw_bytes': None,
        'filename': None,
        'reset': False
    }

    with ui.dialog() as dialog, ui.card().classes(
        'w-[calc(100vw-2rem)] max-w-md p-6 rounded-2xl bg-white border border-slate-200 shadow-2xl gap-3'
    ):
        # 1. Modal Header
        with ui.row().classes('w-full items-center justify-between'):
            with ui.row().classes('items-center gap-2.5'):
                with ui.element('div').classes(
                    'w-9 h-9 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center border border-indigo-100'
                ):
                    ui.icon(icon_name).classes('text-lg')
                ui.label(title).classes('text-base font-bold text-slate-900')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense size=sm color=grey-7')

        ui.label(helper_text).classes('text-xs text-slate-500 leading-relaxed -mt-1')

        # 2. Live Interactive Preview Container
        preview_container = ui.element('div').classes('w-full flex flex-col items-center justify-center py-2')

        def render_preview():
            preview_container.clear()
            with preview_container:
                if is_avatar:
                    with ui.element('div').classes(
                        'w-24 h-24 rounded-full overflow-hidden ring-4 ring-indigo-50 shadow-md '
                        'bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center'
                    ):
                        if staged['url'] and not staged['reset']:
                            ui.image(staged['url']).classes('w-full h-full object-cover')
                        else:
                            ui.label(initials).classes('text-2xl font-black text-white select-none')
                else:
                    with ui.element('div').classes(
                        'w-full h-28 rounded-xl overflow-hidden border border-slate-200 shadow-inner '
                        'bg-gradient-to-r from-indigo-950 via-purple-900 to-slate-950 flex items-center justify-center relative'
                    ):
                        if staged['url'] and not staged['reset']:
                            ui.image(staged['url']).classes('w-full h-full object-cover')
                        else:
                            ui.label('Default Institutional Gradient Active').classes(
                                'text-xs font-semibold text-white/90 px-3 py-1 rounded-full bg-black/40 backdrop-blur-xs'
                            )

                if staged['filename']:
                    with ui.row().classes(
                        'items-center gap-1.5 mt-2.5 px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200'
                    ):
                        ui.icon('check_circle').classes('text-xs')
                        ui.label(f"Staged: {staged['filename']}").classes('text-xs font-semibold truncate max-w-[260px]')

        render_preview()

        # 3. Quasar Uploader wrapped in .libre-dropzone
        async def handle_upload(e):
            try:
                filename, raw_bytes = await extract_upload_file(e)
                if not raw_bytes:
                    ui.notify('No file data received. Please select an image.', type='warning')
                    return
                if len(raw_bytes) > max_bytes:
                    ui.notify(f'File exceeds maximum size ({max_bytes // (1024 * 1024)}MB).', type='negative')
                    return

                import base64
                mime = getattr(e, 'type', None) or 'image/png'
                b64 = base64.b64encode(raw_bytes).decode('utf-8')
                staged['url'] = f'data:{mime};base64,{b64}'
                staged['raw_bytes'] = raw_bytes
                staged['filename'] = filename or e.name
                staged['reset'] = False

                render_preview()
                save_btn.enable()
            except Exception as err:
                ui.notify(f'Upload staging error: {err}', type='negative')

        ui.upload(
            label="Click the + icon or drag & drop photo here",
            auto_upload=True,
            max_files=1,
            on_upload=handle_upload,
            max_file_size=max_bytes
        ).props('accept=".jpg,.jpeg,.png,.webp" flat').classes('libre-dropzone w-full')

        # 4. Save and Reset Handlers
        async def apply_changes():
            save_btn.disable()
            try:
                if staged['reset']:
                    # Reset to default
                    if is_avatar:
                        await mongo_db.update_user_media(user_id, avatar_url=None)
                    else:
                        await mongo_db.update_user_media(user_id, cover_url=None)
                    dialog.close()
                    await on_uploaded(None)
                    ui.notify(f"{'Avatar' if is_avatar else 'Cover photo'} reset to default.", type='positive')
                elif staged['raw_bytes'] and staged['filename']:
                    success, msg, saved_url = save_user_media(
                        user_id, staged['raw_bytes'], staged['filename'], mode
                    )
                    if not success:
                        ui.notify(msg, type='negative')
                        save_btn.enable()
                        return

                    if is_avatar:
                        await mongo_db.update_user_media(user_id, avatar_url=saved_url)
                    else:
                        await mongo_db.update_user_media(user_id, cover_url=saved_url)

                    dialog.close()
                    await on_uploaded(saved_url)
                    ui.notify(f"{'Profile photo' if is_avatar else 'Cover banner'} updated successfully!", type='positive')
            except Exception as err:
                ui.notify(f'Failed to apply changes: {err}', type='negative')
                save_btn.enable()

        def do_reset_default():
            staged['url'] = None
            staged['raw_bytes'] = None
            staged['filename'] = 'Resetting to Default'
            staged['reset'] = True
            render_preview()
            save_btn.enable()

        # 5. Modal Footer (Von Restorff Effect)
        with ui.row().classes('w-full items-center justify-between pt-3 border-t border-slate-100 mt-2'):
            if current_media:
                ui.button('Reset Default', on_click=do_reset_default).props('flat no-caps color=red-6 size=sm').classes(
                    'text-xs font-semibold'
                )
            else:
                ui.element('div')  # Spacer

            with ui.row().classes('items-center gap-2'):
                ui.button('Cancel', on_click=dialog.close).props('outline no-caps color=grey-7 size=sm').classes(
                    'px-3.5 py-1.5 rounded-lg text-xs font-semibold'
                )
                save_btn = ui.button('Save Changes', icon='check', on_click=apply_changes).props(
                    'unelevated no-caps color=indigo size=sm'
                ).classes('px-4 py-1.5 rounded-lg text-xs font-bold shadow-xs transition-all')
                save_btn.disable()

    dialog.open()


def open_avatar_modal(
    user_id: str,
    current_avatar: Optional[str],
    initials: str,
    on_uploaded: Callable[[str], Any]
) -> None:
    """Interactive modal for uploading/previewing circular avatar with 2MB validation."""
    _open_media_upload_modal(
        mode='avatar',
        user_id=user_id,
        current_media=current_avatar,
        initials=initials,
        on_uploaded=on_uploaded
    )


def open_cover_modal(
    user_id: str,
    current_cover: Optional[str],
    on_uploaded: Callable[[str], Any]
) -> None:
    """Interactive modal for uploading/previewing cover banner with 5MB validation."""
    _open_media_upload_modal(
        mode='cover',
        user_id=user_id,
        current_media=current_cover,
        initials='LIBRE',
        on_uploaded=on_uploaded
    )
