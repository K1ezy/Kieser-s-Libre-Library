import base64
import logging
from typing import Callable, Any, Optional
from nicegui import ui, app

from core.database.mongo_manager import mongo_db
from core.utils.media_handler import save_user_media, extract_upload_file
from components.header import refresh_header_avatar

logger = logging.getLogger("MEDIA_MODALS")

MEDIA_UPLOAD_CSS = """
/* Modern Tailwind dropzone for Quasar q-uploader */
.libre-dropzone.q-uploader {
    width: 100% !important;
    max-height: none !important;
    background: #F8FAFC !important;
    border: 2px dashed #CBD5E1 !important;
    border-radius: 1rem !important;
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

/* Scoped Cropper.js Alignment & Precision Crop Overlays */
.cropper-avatar .cropper-view-box,
.cropper-avatar .cropper-face {
    border-radius: 50% !important;
    outline: none !important;
}
.cropper-avatar .cropper-view-box {
    box-shadow: 0 0 0 2px #4f46e5, 0 0 0 9999px rgba(15, 23, 42, 0.82) !important;
}
.cropper-cover .cropper-view-box,
.cropper-cover .cropper-face {
    border-radius: 0.75rem !important;
    outline: none !important;
}
.cropper-cover .cropper-view-box {
    box-shadow: 0 0 0 2px #4f46e5, 0 0 0 9999px rgba(15, 23, 42, 0.82) !important;
}
.cropper-line, .cropper-point {
    background-color: #6366f1 !important;
}
.cropper-point.point-se {
    width: 9px !important;
    height: 9px !important;
}
"""


def _open_media_upload_modal(
    mode: str,
    user_id: str,
    current_media: Optional[str],
    initials: str,
    on_uploaded: Callable[[str], Any]
) -> None:
    """
    DRY media modal featuring pre-confirm align, zoom, rotate, and precision cropping.
    Strictly adheres to 10 Laws of UX (Jakob, Fitts, Hick, Peak-End, Doherty Threshold).
    """
    ui.add_head_html('''
        <link rel="stylesheet" href="/static/js/cropper.min.css">
        <script src="/static/js/cropper.min.js"></script>
    ''')
    ui.add_css(MEDIA_UPLOAD_CSS)

    is_avatar = mode == 'avatar'
    aspect_ratio = 1.0 if is_avatar else 3.1
    target_width = 320 if is_avatar else 1240
    target_height = 320 if is_avatar else 400
    title = 'Update Profile Photo' if is_avatar else 'Update Cover Photo'
    icon_name = 'photo_camera' if is_avatar else 'wallpaper'
    helper_text = (
        'Drag, zoom, and align your photo inside the circular frame (1:1 ratio, Max 2MB).'
        if is_avatar
        else 'Drag, zoom, and align your banner inside the widescreen frame (~3.1:1 ratio, Max 5MB).'
    )
    max_bytes = 2 * 1024 * 1024 if is_avatar else 5 * 1024 * 1024

    staged = {
        'data_url': None,
        'raw_bytes': None,
        'filename': None,
        'reset': False,
        'mode': 'dropzone'  # 'dropzone' or 'editor'
    }

    with ui.dialog() as dialog, ui.card().classes(
        'w-[calc(100vw-2rem)] max-w-lg p-5 sm:p-6 rounded-3xl bg-white border border-slate-200 shadow-2xl gap-3'
    ):
        # 1. Modal Header
        with ui.row().classes('w-full items-center justify-between'):
            with ui.row().classes('items-center gap-2.5'):
                with ui.element('div').classes(
                    'w-9 h-9 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center border border-indigo-100 shadow-2xs'
                ):
                    ui.icon(icon_name).classes('text-lg')
                with ui.column().classes('gap-0'):
                    ui.label(title).classes('text-base font-bold text-slate-900 leading-tight')
                    ui.label('Interactive Align & Precision Crop').classes('text-[10px] font-bold text-indigo-600 tracking-wider uppercase')

            def close_dialog_cleanly():
                ui.run_javascript('if(window.cropper){ window.cropper.destroy(); window.cropper = null; }')
                dialog.close()

            ui.button(icon='close', on_click=close_dialog_cleanly).props('flat round dense size=sm color=grey-7')

        ui.label(helper_text).classes('text-xs text-slate-500 leading-relaxed -mt-1')

        # 2. Main Reactive Content Body Container
        stage_container = ui.element('div').classes('w-full flex flex-col gap-3')

        # Forward references for UI elements in footer
        ui_refs = {'save_btn': None}

        def render_stage():
            stage_container.clear()
            with stage_container:
                if staged['mode'] == 'dropzone':
                    # --- STAGE A: SELECTION DROPZONE & CURRENT PREVIEW ---
                    with ui.element('div').classes('w-full flex flex-col items-center justify-center py-2'):
                        if is_avatar:
                            with ui.element('div').classes(
                                'w-24 h-24 rounded-full overflow-hidden ring-4 ring-indigo-50 shadow-md '
                                'bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center'
                            ):
                                if current_media and not staged['reset']:
                                    ui.image(current_media).classes('w-full h-full object-cover')
                                else:
                                    ui.label(initials).classes('text-2xl font-black text-white select-none')
                        else:
                            with ui.element('div').classes(
                                'w-full h-28 rounded-2xl overflow-hidden border border-slate-200 shadow-inner '
                                'bg-gradient-to-r from-indigo-950 via-purple-900 to-slate-950 flex items-center justify-center relative'
                            ):
                                if current_media and not staged['reset']:
                                    ui.image(current_media).classes('w-full h-full object-cover')
                                else:
                                    ui.label('Default Institutional Banner Active').classes(
                                        'text-xs font-semibold text-white/90 px-3 py-1 rounded-full bg-black/40 backdrop-blur-xs'
                                    )

                        if staged['reset']:
                            with ui.row().classes('items-center gap-1.5 mt-2 px-3 py-1 rounded-full bg-amber-50 text-amber-800 border border-amber-200'):
                                ui.icon('history', size='14px')
                                ui.label('Queued: Reset to Default').classes('text-xs font-semibold')

                    # Upload Dropzone Area
                    async def handle_file_upload(e):
                        try:
                            filename, raw_bytes = await extract_upload_file(e)
                            if not raw_bytes:
                                ui.notify('No file data received. Please select an image.', type='warning')
                                return
                            if len(raw_bytes) > max_bytes:
                                max_mb = max_bytes // (1024 * 1024)
                                ui.notify(f'File exceeds maximum size of {max_mb}MB.', type='negative')
                                return

                            mime = getattr(e, 'type', None) or 'image/png'
                            b64 = base64.b64encode(raw_bytes).decode('utf-8')
                            staged['data_url'] = f'data:{mime};base64,{b64}'
                            staged['raw_bytes'] = raw_bytes
                            staged['filename'] = filename or getattr(e, 'name', 'photo.png')
                            staged['reset'] = False
                            staged['mode'] = 'editor'

                            render_stage()
                            if ui_refs['save_btn']:
                                ui_refs['save_btn'].enable()
                        except Exception as err:
                            logger.error(f"Upload error: {err}")
                            ui.notify(f'Upload failed: {err}', type='negative')

                    ui.upload(
                        label="Click the + icon or drag & drop photo here to align & crop",
                        auto_upload=True,
                        max_files=1,
                        on_upload=handle_file_upload,
                        max_file_size=max_bytes
                    ).props('accept=".jpg,.jpeg,.png,.webp" flat').classes('libre-dropzone w-full')

                else:
                    # --- STAGE B: INTERACTIVE ALIGN, CROP & SCALE VIEWPORT ---
                    with ui.element('div').classes(
                        'w-full max-h-[300px] sm:max-h-[340px] bg-slate-950 rounded-2xl overflow-hidden '
                        'relative shadow-inner border border-slate-800 flex items-center justify-center p-1.5'
                    ):
                        ui.html(f'''
                            <div style="width: 100%; max-height: 290px; display: flex; align-items: center; justify-content: center;">
                                <img id="libre-crop-target" src="{staged['data_url']}" style="display: block; max-width: 100%; max-height: 270px;">
                            </div>
                        ''', sanitize=False).classes('w-full')

                    # Initialize Cropper.js in browser
                    crop_mask_class = 'cropper-avatar' if is_avatar else 'cropper-cover'
                    ui.run_javascript(f'''
                        setTimeout(() => {{
                            const target = document.getElementById('libre-crop-target');
                            if (!target) return;
                            if (window.cropper) {{
                                window.cropper.destroy();
                            }}
                            window.cropper = new Cropper(target, {{
                                aspectRatio: {aspect_ratio},
                                viewMode: 1,
                                autoCropArea: 0.92,
                                background: false,
                                dragMode: 'move',
                                responsive: true,
                                guides: true,
                                center: true,
                                highlight: false,
                                cropBoxMovable: true,
                                cropBoxResizable: true,
                                toggleDragModeOnDblclick: false,
                                ready() {{
                                    const c = document.querySelector('.cropper-container');
                                    if (c) {{
                                        c.classList.add('{crop_mask_class}');
                                    }}
                                }}
                            }});
                        }}, 100);
                    ''')

                    # Real-Time Calibration Controls (Hick's & Fitts's Law)
                    with ui.column().classes('w-full gap-2 p-3 rounded-2xl bg-slate-50 border border-slate-200/80'):
                        with ui.row().classes('w-full items-center justify-between'):
                            ui.label('ALIGNMENT & ZOOM').classes('text-[10px] font-black text-slate-500 tracking-wider uppercase')
                            ui.label('Pinch / scroll or slide').classes('text-[10px] font-medium text-slate-400')

                        with ui.row().classes('w-full items-center gap-2.5'):
                            ui.button(
                                icon='zoom_out',
                                on_click=lambda: ui.run_javascript('if(window.cropper) window.cropper.zoom(-0.1);')
                            ).props('flat round dense size=sm color=grey-8').tooltip('Zoom Out')

                            zoom_slider = ui.slider(min=0.2, max=3.0, step=0.02, value=1.0) \
                                .classes('flex-1') \
                                .props('color=indigo track-color=indigo-2')

                            def on_zoom(e):
                                ui.run_javascript(f'if(window.cropper) window.cropper.zoomTo({float(e.value)});')

                            zoom_slider.on('update:model-value', on_zoom)

                            ui.button(
                                icon='zoom_in',
                                on_click=lambda: ui.run_javascript('if(window.cropper) window.cropper.zoom(0.1);')
                            ).props('flat round dense size=sm color=grey-8').tooltip('Zoom In')

                        with ui.row().classes('w-full items-center justify-between gap-2 pt-1 border-t border-slate-200/60 flex-wrap'):
                            with ui.row().classes('items-center gap-1.5'):
                                ui.button(
                                    'Rotate Left',
                                    icon='rotate_left',
                                    on_click=lambda: ui.run_javascript('if(window.cropper) window.cropper.rotate(-90);')
                                ).props('outline dense size=xs color=grey-8 no-caps').classes('px-2.5 py-1 rounded-lg text-xs font-semibold')

                                ui.button(
                                    'Rotate Right',
                                    icon='rotate_right',
                                    on_click=lambda: ui.run_javascript('if(window.cropper) window.cropper.rotate(90);')
                                ).props('outline dense size=xs color=grey-8 no-caps').classes('px-2.5 py-1 rounded-lg text-xs font-semibold')

                                ui.button(
                                    'Reset',
                                    icon='restart_alt',
                                    on_click=lambda: (
                                        ui.run_javascript('if(window.cropper) window.cropper.reset();'),
                                        zoom_slider.set_value(1.0)
                                    )
                                ).props('flat dense size=xs color=grey-7 no-caps').classes('px-2 py-1 rounded-lg text-xs font-semibold').tooltip('Reset Alignment & Zoom')

                            def switch_back_to_dropzone():
                                ui.run_javascript('if(window.cropper){ window.cropper.destroy(); window.cropper = null; }')
                                staged['mode'] = 'dropzone'
                                render_stage()

                            ui.button(
                                'Change Photo',
                                icon='add_photo_alternate',
                                on_click=switch_back_to_dropzone
                            ).props('flat dense size=xs color=indigo no-caps').classes('text-xs font-bold')

        # 3. Save Changes Handler with Real-Time Viewport Crop Export
        async def confirm_and_save():
            if ui_refs['save_btn']:
                ui_refs['save_btn'].disable()

            try:
                if staged['reset']:
                    # Reset to default state
                    if is_avatar:
                        await mongo_db.update_user_media(user_id, avatar_url=None)
                        app.storage.user['avatar_url'] = ''
                    else:
                        await mongo_db.update_user_media(user_id, cover_url=None)
                        app.storage.user['cover_url'] = ''

                    close_dialog_cleanly()
                    await on_uploaded(None)
                    refresh_header_avatar()
                    ui.notify(f"{'Avatar' if is_avatar else 'Cover banner'} reset to default.", type='positive')
                    return

                final_b64 = None
                if staged['mode'] == 'editor':
                    # Extract high-quality cropped canvas from Cropper.js instance
                    crop_js = f'''
                        return (() => {{
                            try {{
                                if (!window.cropper) return null;
                                const canvas = window.cropper.getCroppedCanvas({{
                                    width: {target_width},
                                    height: {target_height},
                                    imageSmoothingEnabled: true,
                                    imageSmoothingQuality: 'high'
                                }});
                                if (!canvas) return null;
                                return canvas.toDataURL('image/jpeg', 0.92);
                            }} catch (e) {{
                                console.error("Cropper export error:", e);
                                return null;
                            }}
                        }})();
                    '''
                    try:
                        final_b64 = await ui.run_javascript(crop_js, timeout=10.0)
                    except Exception as js_err:
                        logger.warning(f"JS Cropper export timed out or failed: {js_err}")

                # Decode into raw bytes
                if final_b64 and isinstance(final_b64, str) and final_b64.startswith('data:'):
                    b64_payload = final_b64.split(',', 1)[1]
                    file_bytes = base64.b64decode(b64_payload)
                    file_name = f"{'avatar' if is_avatar else 'cover'}.jpg"
                elif staged['raw_bytes']:
                    # Resilient fallback if client crop script was unavailable
                    file_bytes = staged['raw_bytes']
                    file_name = staged['filename'] or 'photo.jpg'
                else:
                    ui.notify('No image selected to save.', type='warning')
                    if ui_refs['save_btn']:
                        ui_refs['save_btn'].enable()
                    return

                # Save to disk with cache-busting
                success, msg, saved_url = save_user_media(user_id, file_bytes, file_name, mode)
                if not success:
                    ui.notify(msg, type='negative')
                    if ui_refs['save_btn']:
                        ui_refs['save_btn'].enable()
                    return

                # Save to MongoDB
                if is_avatar:
                    await mongo_db.update_user_media(user_id, avatar_url=saved_url)
                    app.storage.user['avatar_url'] = saved_url
                else:
                    await mongo_db.update_user_media(user_id, cover_url=saved_url)
                    app.storage.user['cover_url'] = saved_url

                close_dialog_cleanly()
                await on_uploaded(saved_url)
                refresh_header_avatar()
                ui.notify(
                    f"{'Profile photo' if is_avatar else 'Cover banner'} aligned & saved successfully!",
                    type='positive',
                    position='bottom',
                    icon='verified'
                )
            except Exception as err:
                logger.error(f"Save error: {err}")
                ui.notify(f"Failed to apply changes: {err}", type='negative')
                if ui_refs['save_btn']:
                    ui_refs['save_btn'].enable()

        def do_reset_default():
            staged['data_url'] = None
            staged['raw_bytes'] = None
            staged['filename'] = None
            staged['reset'] = True
            staged['mode'] = 'dropzone'
            render_stage()
            if ui_refs['save_btn']:
                ui_refs['save_btn'].enable()

        # 4. Modal Footer (Von Restorff Effect)
        with ui.row().classes('w-full items-center justify-between pt-3 border-t border-slate-100 mt-1'):
            if current_media:
                ui.button('Reset Default', on_click=do_reset_default).props('flat no-caps color=red-6 size=sm').classes(
                    'text-xs font-semibold'
                )
            else:
                ui.element('div')  # Spacer

            with ui.row().classes('items-center gap-2'):
                ui.button('Cancel', on_click=close_dialog_cleanly).props('outline no-caps color=grey-7 size=sm').classes(
                    'px-3.5 py-1.5 rounded-lg text-xs font-semibold'
                )
                ui_refs['save_btn'] = ui.button(
                    'Confirm & Save',
                    icon='check',
                    on_click=confirm_and_save
                ).props('unelevated no-caps size=sm').classes(
                    'px-4.5 py-1.5 rounded-lg text-xs font-bold bg-indigo-600 hover:bg-indigo-700 '
                    'text-white shadow-xs transition-all'
                )
                ui_refs['save_btn'].disable()

        # Initial render of dropzone stage
        render_stage()

    dialog.open()


def open_avatar_modal(
    user_id: str,
    current_avatar: Optional[str],
    initials: str,
    on_uploaded: Callable[[str], Any]
) -> None:
    """Interactive modal with circular alignment, zoom, rotation, and 2MB validation."""
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
    """Interactive modal with widescreen alignment, zoom, rotation, and 5MB validation."""
    _open_media_upload_modal(
        mode='cover',
        user_id=user_id,
        current_media=current_cover,
        initials='LIBRE',
        on_uploaded=on_uploaded
    )

