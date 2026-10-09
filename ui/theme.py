from nicegui import ui, app
from core.config import settings

# --- MODERN CLEAN LIGHT DESIGN SYSTEM ---
GLOBAL_THEME_STYLES = '''
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <meta name="theme-color" content="#4f46e5">
    <meta name="color-scheme" content="light">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        :root {
            color-scheme: light !important;
            --font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            --safe-area-top: env(safe-area-inset-top, 0px);
            --safe-area-bottom: env(safe-area-inset-bottom, 0px);
            --safe-area-left: env(safe-area-inset-left, 0px);
            --safe-area-right: env(safe-area-inset-right, 0px);
        }

        *, *::before, *::after {
            box-sizing: border-box;
            -webkit-tap-highlight-color: transparent;
        }

        /* Permanently enforce clean, coherent light theme across all devices & mobile OS settings */
        html, body, body.body--dark {
            overflow-x: hidden;
            max-width: 100vw;
            width: 100%;
            font-family: var(--font-family) !important;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
            touch-action: manipulation;
            overscroll-behavior-y: none;
            -webkit-overflow-scrolling: touch;
            background-color: #f8fafc !important; /* Tailwind slate-50 */
            color: #0f172a !important;            /* Tailwind slate-900 */
        }

        /* Neutralize Quasar dark mode artifacts on body or child elements */
        body.body--dark .bg-white,
        .bg-white {
            background-color: #ffffff !important;
            color: #0f172a !important;
        }

        body.body--dark .bg-slate-50,
        .bg-slate-50 {
            background-color: #f8fafc !important;
        }

        body.body--dark .text-slate-900,
        .text-slate-900 {
            color: #0f172a !important;
        }

        body.body--dark .text-slate-800,
        .text-slate-800 {
            color: #1e293b !important;
        }

        body.body--dark .text-slate-700,
        .text-slate-700 {
            color: #334155 !important;
        }

        body.body--dark .text-slate-500,
        .text-slate-500 {
            color: #64748b !important;
        }

        body.body--dark .text-slate-400,
        .text-slate-400 {
            color: #94a3b8 !important;
        }

        /* Quasar components light mode enforcement */
        .q-header {
            background-color: rgba(255, 255, 255, 0.95) !important;
            color: #0f172a !important;
            border-bottom: 1px solid #e2e8f0 !important;
        }

        .q-drawer {
            background-color: #ffffff !important;
            color: #0f172a !important;
            border-right: 1px solid #e2e8f0 !important;
        }

        .q-dialog .q-card,
        .q-menu {
            background-color: #ffffff !important;
            color: #0f172a !important;
            border: 1px solid #e2e8f0 !important;
        }

        .q-field--outlined .q-field__control {
            background-color: #ffffff !important;
            border-color: #cbd5e1 !important;
        }

        .q-field__native,
        .q-field__input {
            color: #0f172a !important;
        }

        /* Prevent iOS automatic zoom on focus while retaining clear legibility */
        @media (max-width: 768px) {
            input, select, textarea, .q-field__native, .q-field__input {
                font-size: 16px !important;
            }
            .q-btn:active {
                transform: scale(0.97);
            }
        }

        .touch-pan-x {
            touch-action: pan-x;
            -webkit-overflow-scrolling: touch;
        }

        .touch-pan-y {
            touch-action: pan-y;
            -webkit-overflow-scrolling: touch;
        }

        /* Responsive Text and Preformatted Code Blocks */
        pre, code {
            max-width: 100%;
            overflow-x: auto;
            white-space: pre-wrap;
            word-break: break-word;
        }

        table {
            max-width: 100%;
            overflow-x: auto;
            display: block;
        }

        img {
            max-width: 100%;
            height: auto;
        }

        /* Custom Sleek Light Scrollbars */
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        ::-webkit-scrollbar-track {
            background: transparent;
        }
        ::-webkit-scrollbar-thumb {
            background: rgba(148, 163, 184, 0.4);
            border-radius: 9999px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(99, 102, 241, 0.7);
        }

        /* Accessibility Focus-Visible High-Contrast Indicators (WCAG 2.1 AA/AAA) */
        *:focus-visible {
            outline: 2px solid #4f46e5 !important;
            outline-offset: 2px !important;
            box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.25) !important;
        }
        button:focus-visible, a:focus-visible, .q-btn:focus-visible {
            outline: 2px solid #4f46e5 !important;
            outline-offset: 3px !important;
            box-shadow: 0 0 0 5px rgba(99, 102, 241, 0.2) !important;
        }

        /* Keyboard Navigation: Chord Feedback Pill */
        .libre-chord-indicator {
            position: fixed;
            bottom: 24px;
            left: 50%;
            transform: translateX(-50%) translateY(100px);
            background: rgba(15, 23, 42, 0.94);
            color: #ffffff;
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            padding: 8px 18px;
            border-radius: 9999px;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 8px 10px -6px rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.15);
            display: flex;
            align-items: center;
            gap: 10px;
            z-index: 9999;
            font-size: 13px;
            pointer-events: none;
            opacity: 0;
            transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .libre-chord-indicator.visible {
            transform: translateX(-50%) translateY(0);
            opacity: 1;
        }
        .libre-chord-indicator .chord-badge {
            background: #4f46e5;
            color: #ffffff;
            font-weight: 800;
            font-size: 11px;
            padding: 2px 7px;
            border-radius: 6px;
            border: 1px solid rgba(255, 255, 255, 0.25);
            text-transform: uppercase;
        }
        .libre-chord-indicator .chord-text {
            color: #e2e8f0;
            font-weight: 500;
        }
        .libre-chord-indicator .chord-text b {
            color: #818cf8;
            font-weight: 700;
        }

        /* Keyboard Shortcuts Help Modal */
        .libre-shortcuts-modal {
            position: fixed;
            inset: 0;
            z-index: 99999;
            display: flex;
            align-items: center;
            justify-content: center;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.2s ease;
            padding: 16px;
        }
        .libre-shortcuts-modal.visible {
            opacity: 1;
            pointer-events: auto;
        }
        .libre-shortcuts-modal .modal-backdrop {
            position: absolute;
            inset: 0;
            background: rgba(15, 23, 42, 0.6);
            backdrop-filter: blur(4px);
            -webkit-backdrop-filter: blur(4px);
        }
        .libre-shortcuts-modal .modal-card {
            position: relative;
            background: #ffffff;
            border-radius: 24px;
            border: 1px solid #e2e8f0;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
            max-width: 680px;
            width: 100%;
            max-height: 88vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            transform: scale(0.96) translateY(10px);
            transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .libre-shortcuts-modal.visible .modal-card {
            transform: scale(1) translateY(0);
        }
        .libre-shortcuts-modal .modal-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 20px 24px 16px;
            border-bottom: 1px solid #f1f5f9;
        }
        .libre-shortcuts-modal .modal-title-group {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .libre-shortcuts-modal .modal-icon {
            font-size: 26px;
            line-height: 1;
        }
        .libre-shortcuts-modal .modal-title {
            margin: 0;
            font-size: 18px;
            font-weight: 800;
            color: #0f172a;
            letter-spacing: -0.02em;
        }
        .libre-shortcuts-modal .modal-subtitle {
            margin: 2px 0 0;
            font-size: 12px;
            color: #64748b;
        }
        .libre-shortcuts-modal .modal-close-btn {
            background: transparent;
            border: none;
            color: #94a3b8;
            font-size: 18px;
            cursor: pointer;
            padding: 8px;
            border-radius: 50%;
            line-height: 1;
            transition: all 0.15s;
        }
        .libre-shortcuts-modal .modal-close-btn:hover {
            color: #0f172a;
            background: #f1f5f9;
        }
        .libre-shortcuts-modal .modal-body {
            padding: 20px 24px;
            overflow-y: auto;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }
        @media (max-width: 640px) {
            .libre-shortcuts-modal .modal-body {
                grid-template-columns: 1fr;
                gap: 14px;
            }
        }
        .libre-shortcuts-modal .shortcut-group {
            background: #f8fafc;
            border: 1px solid #f1f5f9;
            border-radius: 16px;
            padding: 14px 16px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .libre-shortcuts-modal .shortcut-group.full-width {
            grid-column: 1 / -1;
        }
        .libre-shortcuts-modal .group-title {
            font-size: 12px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #4f46e5;
            margin-bottom: 2px;
        }
        .libre-shortcuts-modal .shortcut-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
        }
        .libre-shortcuts-modal .shortcut-desc {
            font-size: 13px;
            font-weight: 500;
            color: #334155;
        }
        .libre-shortcuts-modal .key-combo {
            display: flex;
            align-items: center;
            gap: 4px;
            font-size: 11px;
            color: #64748b;
        }
        .libre-shortcuts-modal kbd {
            background: #ffffff;
            border: 1px solid #cbd5e1;
            border-bottom: 2px solid #94a3b8;
            border-radius: 6px;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
            color: #0f172a;
            font-family: inherit;
            font-size: 11px;
            font-weight: 700;
            padding: 2px 7px;
            min-width: 22px;
            text-align: center;
            display: inline-block;
        }
        .libre-shortcuts-modal .grid-shortcuts {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px 20px;
        }
        @media (max-width: 640px) {
            .libre-shortcuts-modal .grid-shortcuts {
                grid-template-columns: 1fr;
            }
        }
        .libre-shortcuts-modal .modal-footer {
            padding: 14px 24px;
            border-top: 1px solid #f1f5f9;
            background: #ffffff;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .libre-shortcuts-modal .footer-hint {
            font-size: 12px;
            color: #64748b;
        }
        .libre-shortcuts-modal .footer-btn {
            background: #4f46e5;
            color: #ffffff;
            border: none;
            padding: 8px 18px;
            border-radius: 12px;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            transition: background 0.15s;
        }
        .libre-shortcuts-modal .footer-btn:hover {
            background: #4338ca;
        }
    </style>
    <script src="/static/js/keyboard_navigation.js" defer></script>
'''

def apply_theme():
    """Applies clean, unified light design tokens, Inter typography, and crisp palette."""
    ui.add_head_html(GLOBAL_THEME_STYLES)
    ui.colors(
        primary="#4f46e5",    # Indigo 600
        secondary="#6366f1",  # Indigo 500
        accent="#7c3aed",     # Purple 600
        positive="#10b981",   # Emerald 500
        negative="#f43f5e",   # Rose 500
        info="#0ea5e9",       # Sky 500
        warning="#f59e0b"     # Amber 500
    )
    ui.dark_mode().disable()
    if 'dark_mode' in app.storage.user:
        app.storage.user.pop('dark_mode', None)
    ui.run_javascript("""
        document.documentElement.classList.remove('dark');
        document.body.classList.remove('body--dark');
        if (window.Quasar && window.Quasar.dark) {
            window.Quasar.dark.set(false);
        }
    """)