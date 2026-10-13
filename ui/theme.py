from nicegui import ui, app
from core.config import settings

# --- MODERN CLEAN LIGHT DESIGN SYSTEM ---
GLOBAL_THEME_STYLES = '''
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <meta name="theme-color" content="#4f46e5">
    <meta name="color-scheme" content="light">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            color-scheme: light !important;
            --font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
            --safe-area-top: env(safe-area-inset-top, 0px);
            --safe-area-bottom: env(safe-area-inset-bottom, 0px);
            --safe-area-left: env(safe-area-inset-left, 0px);
            --safe-area-right: env(safe-area-inset-right, 0px);
        }

        *, *::before, *::after {
            box-sizing: border-box;
            -webkit-tap-highlight-color: transparent;
        }

        /* Permanently enforce clean, coherent light theme and standard vertical scrolling */
        html, body, body.body--dark {
            min-height: 100%;
            height: auto;
            max-width: 100vw;
            width: 100%;
            overflow-x: hidden;
            overflow-y: auto;
            -webkit-overflow-scrolling: touch;
            font-family: var(--font-family) !important;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
            background-color: #f8fafc !important; /* Tailwind slate-50 */
            color: #0f172a !important;            /* Tailwind slate-900 */
        }

        /* Quasar & NiceGUI Root Layout Containers - Unfreeze Touch Momentum */
        #q-app, .q-layout, .q-page-container {
            min-height: 100% !important;
            height: auto !important;
            width: 100% !important;
            overflow-x: hidden !important;
            overflow-y: visible !important;
            -webkit-overflow-scrolling: touch !important;
        }

        /* Native touch momentum for scrollable viewports */
        .overflow-y-auto, [class*="overflow-y-auto"] {
            -webkit-overflow-scrolling: touch !important;
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

        /* =========================================================================
           STRICT Z-INDEX & QUASAR PORTAL HIERARCHY
           Base Content: z-0 to z-10 | Header: z-30 | Bottom Nav: z-35
           Drawers: z-45 | Dialogs: z-6000 | Menus/Selects: z-7000
           Tooltips: z-8000 | System Notifications: z-9000
           ========================================================================= */
        .q-header {
            z-index: 30 !important;
            background-color: rgba(255, 255, 255, 0.95) !important;
            color: #0f172a !important;
            border-bottom: 1px solid #e2e8f0 !important;
        }

        nav.fixed.bottom-0, [class*="fixed bottom-0"] {
            z-index: 35 !important;
        }

        .q-drawer {
            z-index: 45 !important;
            background-color: #ffffff !important;
            color: #0f172a !important;
            border-right: 1px solid #e2e8f0 !important;
        }

        .q-dialog {
            z-index: 6000 !important;
        }

        .q-dialog .q-card {
            background-color: #ffffff !important;
            color: #0f172a !important;
            border: 1px solid #e2e8f0 !important;
            max-height: calc(100dvh - 2rem) !important;
        }

        /* Quasar Menus, Dropdown Popovers, and Select Options */
        .q-menu, .q-select__menu, .q-virtual-scroll {
            z-index: 7000 !important;
            background-color: #ffffff !important;
            color: #0f172a !important;
            border: 1px solid #e2e8f0 !important;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04) !important;
            border-radius: 16px !important;
        }

        .q-tooltip {
            z-index: 8000 !important;
        }

        .q-notifications {
            z-index: 9000 !important;
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

        /* =========================================================================
           GPU LAYER PROMOTION & MOBILE PERFORMANCE OPTIMIZATIONS
           ========================================================================= */
        .q-header, nav.fixed.bottom-0, [class*="fixed bottom-0"] {
            -webkit-transform: translateZ(0);
            transform: translateZ(0);
            will-change: transform;
        }

        /* Eliminate GPU blur rasterization thrashing on mobile viewports */
        @media (max-width: 640px) {
            .backdrop-blur-md, .backdrop-blur-sm, [class*="backdrop-blur"] {
                backdrop-filter: none !important;
                -webkit-backdrop-filter: none !important;
            }
            .q-header {
                background-color: #ffffff !important;
            }
            nav.fixed.bottom-0, [class*="fixed bottom-0"] {
                background-color: #ffffff !important;
            }
        }

        /* Virtual card layout containment to boost scroll FPS */
        .book-card-item {
            content-visibility: auto;
            contain-intrinsic-size: 160px 240px;
        }

        @media (max-width: 768px) {
            .group:hover .group-hover\:scale-105,
            .group:hover .group-hover\:scale-110 {
                transform: none !important;
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

        /* Dedicated Document Synopsis Typography & Scroll Styles */
        .synopsis-scroll-container {
            max-height: 280px;
            overflow-y: auto;
            overscroll-behavior-y: contain;
            -webkit-overflow-scrolling: touch;
            touch-action: pan-y;
            scrollbar-width: thin;
            scrollbar-color: rgba(148, 163, 184, 0.5) transparent;
        }

        @media (min-width: 640px) {
            .synopsis-scroll-container {
                max-height: 320px;
            }
        }

        @media (min-width: 1024px) {
            .synopsis-scroll-container {
                max-height: 360px;
            }
        }

        .synopsis-markdown,
        .synopsis-markdown * {
            font-family: var(--font-family) !important;
        }

        .synopsis-markdown p {
            margin-bottom: 0.85rem !important;
            line-height: 1.75 !important;
            color: #334155 !important;
            font-size: 0.9375rem !important;
            letter-spacing: -0.01em !important;
        }

        .synopsis-markdown p:last-child {
            margin-bottom: 0 !important;
        }

        .synopsis-markdown h1,
        .synopsis-markdown h2,
        .synopsis-markdown h3,
        .synopsis-markdown h4 {
            font-weight: 700 !important;
            color: #0f172a !important;
            margin-top: 1rem !important;
            margin-bottom: 0.5rem !important;
            line-height: 1.4 !important;
            font-size: 1.05rem !important;
        }

        .synopsis-markdown ul,
        .synopsis-markdown ol {
            margin-top: 0.5rem !important;
            margin-bottom: 0.85rem !important;
            padding-left: 1.4rem !important;
            color: #334155 !important;
            font-size: 0.9375rem !important;
            line-height: 1.7 !important;
        }

        .synopsis-markdown li {
            margin-bottom: 0.35rem !important;
        }

        .synopsis-markdown strong,
        .synopsis-markdown b {
            font-weight: 700 !important;
            color: #1e293b !important;
        }

        .synopsis-markdown em,
        .synopsis-markdown i {
            font-style: italic !important;
        }

        .synopsis-markdown hr {
            border: 0 !important;
            border-top: 1px solid #e2e8f0 !important;
            margin: 0.85rem 0 !important;
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

        /* =========================================================================
           MOBILE RESPONSIVENESS & ADAPTIVE VIEWPORT ENGINE
           ========================================================================= */
        /* 1. Fluid Book Catalog Grid: Exactly 2 fluid columns on 340-500px phones,
           1 column on <340px, scaling cleanly to 3-6 columns on larger screens */
        .fluid-book-grid {
            display: grid !important;
            grid-template-columns: repeat(auto-fill, minmax(clamp(130px, 44vw, 195px), 1fr)) !important;
            gap: clamp(10px, 2.5vw, 20px) !important;
            width: 100% !important;
        }
        @media (max-width: 340px) {
            .fluid-book-grid {
                grid-template-columns: 1fr !important;
            }
        }

        /* 2. Touch Target and Safe-Area Insets for Notches & Gesture Bars */
        .safe-pb {
            padding-bottom: max(16px, env(safe-area-inset-bottom, 16px)) !important;
        }
        .safe-pt {
            padding-top: max(12px, env(safe-area-inset-top, 12px)) !important;
        }
        .safe-pl {
            padding-left: max(12px, env(safe-area-inset-left, 12px)) !important;
        }
        .safe-pr {
            padding-right: max(12px, env(safe-area-inset-right, 12px)) !important;
        }

        /* 3. Mobile Card-Stack Transformation for Tables on <768px */
        @media (max-width: 768px) {
            .mobile-card-table .q-table__middle {
                overflow-x: hidden !important;
            }
            .mobile-card-table .q-table thead {
                display: none !important;
            }
            .mobile-card-table .q-table tbody tr {
                display: flex !important;
                flex-direction: column !important;
                margin-bottom: 12px !important;
                border: 1px solid #e2e8f0 !important;
                border-radius: 18px !important;
                background-color: #ffffff !important;
                padding: 14px 16px !important;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04) !important;
            }
            .mobile-card-table .q-table tbody td {
                display: flex !important;
                justify-content: space-between !important;
                align-items: center !important;
                border-bottom: 1px solid #f1f5f9 !important;
                padding: 8px 0 !important;
                font-size: 13px !important;
                min-height: 36px !important;
            }
            .mobile-card-table .q-table tbody td:last-child {
                border-bottom: none !important;
                padding-top: 10px !important;
            }
            .mobile-card-table .q-table tbody td::before {
                content: attr(data-label);
                font-weight: 700;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: #64748b;
            }
        }

        /* 4. Mobile Bottom-Sheet Transformation for Modals & Dialogs on <640px */
        @media (max-width: 640px) {
            .q-dialog__inner--minimized > div {
                max-width: 100vw !important;
                width: 100vw !important;
                border-bottom-left-radius: 0 !important;
                border-bottom-right-radius: 0 !important;
                border-top-left-radius: 28px !important;
                border-top-right-radius: 28px !important;
                position: fixed !important;
                bottom: 0 !important;
                margin: 0 !important;
                max-height: 85dvh !important;
                overflow-y: auto !important;
                padding-bottom: max(20px, env(safe-area-inset-bottom, 20px)) !important;
            }
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