/**
 * Libre EPUB Reader - Core Lifecycle & Navigation Coordinator
 * Orchestrates ePub.js rendering, telemetry, progress syncing, and user input.
 */
(function() {
    'use strict';

    // 1. Initialization Parameters
    const urlParams = new URLSearchParams(window.location.search);
    const bookUrl = urlParams.get('file');
    const bookId = urlParams.get('book_id') || '';
    const userId = urlParams.get('user_id') || 'guest';
    const initialCfi = urlParams.get('cfi') ? decodeURIComponent(urlParams.get('cfi')) : null;
    const initialPage = parseInt(urlParams.get('page') || '1', 10);
    const totalPages = Math.max(1, parseInt(urlParams.get('total') || '100', 10));

    const errorDiv = document.getElementById('error-msg');
    const pageInfo = document.getElementById('page-info');
    const toastDiv = document.getElementById('reader-toast');
    let toastTimer = null;

    if (!bookUrl) {
        if (errorDiv) {
            errorDiv.style.display = 'block';
            errorDiv.innerText = "Error: No book file specified in query parameters.";
        }
        return;
    }

    let book = null;
    let rendition = null;
    let isRestoring = Boolean(initialCfi || (initialPage > 1));
    let lastNotifiedCfi = initialCfi || null;
    let lastNotifiedPage = initialPage;
    let saveDebounceTimer = null;
    let pendingSavePayload = null;

    // 2. Global Reader Utilities
    function showToast(msg) {
        if (!toastDiv) return;
        toastDiv.innerText = msg;
        toastDiv.classList.add('show');
        if (toastTimer) clearTimeout(toastTimer);
        toastTimer = setTimeout(() => toastDiv.classList.remove('show'), 2400);
    }

    function dismissAllPopovers() {
        const ids = ['selection-popover', 'pop-note-container', 'highlight-popover', 'ai-explainer-card'];
        ids.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = 'none';
        });
    }

    // 3. Progress Synchronization & Telemetry
    const ProgressSync = {
        updateHud(page, total, pct, cfi) {
            if (pageInfo) pageInfo.innerText = `Page ${page} of ${total} (${pct}%)`;
            try {
                window.parent.postMessage({
                    type: 'LIBRE_READER_PROGRESS',
                    book_id: bookId,
                    current_page: page,
                    total_pages: total,
                    percentage: pct,
                    cfi: cfi,
                    theme: window.ThemeManager.currentTheme,
                    font_size: window.ThemeManager.currentFontSize,
                    font_family: window.ThemeManager.currentFontFamily,
                    line_height: window.ThemeManager.currentLineHeight
                }, '*');
            } catch (err) {}
        },

        scheduleSave(payload) {
            pendingSavePayload = {
                ...payload,
                theme: window.ThemeManager.currentTheme,
                font_size: window.ThemeManager.currentFontSize,
                font_family: window.ThemeManager.currentFontFamily,
                line_height: window.ThemeManager.currentLineHeight
            };
            if (saveDebounceTimer) clearTimeout(saveDebounceTimer);
            saveDebounceTimer = setTimeout(() => this.persistReadingProgress(pendingSavePayload), 500);
        },

        async persistReadingProgress(payload) {
            if (!payload || !payload.book_id) return;
            try {
                await fetch('/api/progress/sync', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
            } catch (err) {
                console.error("[EPUB Progress] Persist error:", err);
            }
        },

        flushPendingSave() {
            if (!pendingSavePayload) return;
            const data = JSON.stringify(pendingSavePayload);
            if (navigator.sendBeacon) {
                navigator.sendBeacon('/api/progress/sync', new Blob([data], { type: 'application/json' }));
            } else {
                fetch('/api/progress/sync', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: data, keepalive: true });
            }
            pendingSavePayload = null;
        }
    };

    window.addEventListener('beforeunload', () => ProgressSync.flushPendingSave());
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') ProgressSync.flushPendingSave();
    });

    // 4. Keyboard Shortcuts & Parent Navigation
    function handleKeyDown(e) {
        if (e.target && ['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return;
        if (e.key === "ArrowLeft" || e.key === "PageUp" || e.key === "j") {
            if (rendition) rendition.prev();
            e.preventDefault();
        } else if (e.key === "ArrowRight" || e.key === "PageDown" || e.key === "k") {
            if (rendition) rendition.next();
            e.preventDefault();
        } else if (e.key === "t" || e.key === "T") {
            window.ThemeManager.cycleTheme();
            e.preventDefault();
        } else if (e.key === "h" || e.key === "H") {
            window.AnnotationManager.toggleDrawer();
            e.preventDefault();
        } else if (e.key === "+" || e.key === "=") {
            window.ThemeManager.applyFontSize(window.ThemeManager.currentFontSize + 1, true);
            e.preventDefault();
        } else if (e.key === "-" || e.key === "_") {
            window.ThemeManager.applyFontSize(window.ThemeManager.currentFontSize - 1, true);
            e.preventDefault();
        } else if (e.key === "Escape") {
            dismissAllPopovers();
            const pop = document.getElementById('appearance-popover');
            const drawer = document.getElementById('annotations-drawer');
            if (pop) pop.style.display = 'none';
            if (drawer) drawer.classList.remove('open');
        }
    }

    document.addEventListener("keydown", handleKeyDown);

    window.addEventListener('message', (e) => {
        if (!e.data || !rendition) return;
        if (e.data.type === 'READER_NAVIGATE') {
            if (e.data.action === 'next') rendition.next();
            else if (e.data.action === 'prev') rendition.prev();
        } else if (e.data.type === 'SET_THEME' && e.data.theme) {
            window.ThemeManager.applyTheme(e.data.theme, true);
        }
    });

    document.addEventListener('click', (e) => {
        const popovers = ['selection-popover', 'highlight-popover', 'ai-explainer-card'];
        popovers.forEach(id => {
            const el = document.getElementById(id);
            if (el && !el.contains(e.target) && e.target !== el) el.style.display = 'none';
        });
    });

    // 5. Initialize Sub-Modules
    window.ThemeManager.init();

    window.AnnotationManager.init({
        bookId,
        userId,
        getRendition: () => rendition,
        getPageNum: () => lastNotifiedPage,
        showToast,
        dismissAllPopovers
    });

    window.TarsExplainer.init({
        bookId,
        showToast,
        dismissAllPopovers
    });

    // 6. Launch ePub.js Engine
    try {
        book = ePub(bookUrl);
        rendition = book.renderTo("viewer", {
            width: "100%",
            height: "100%",
            flow: "paginated",
            manager: "default"
        });

        window.ThemeManager.setRendition(rendition);

        if (initialCfi) {
            rendition.display(initialCfi).catch(() => rendition.display());
        } else {
            rendition.display();
        }

        window.AnnotationManager.fetchAnnotations();

        // Passage Selection Listener
        rendition.on('selected', (cfiRange, contents) => {
            window.AnnotationManager.activeCfiRange = cfiRange;
            try {
                const iframe = document.querySelector('#viewer iframe');
                const iframeRect = iframe ? iframe.getBoundingClientRect() : { left: 0, top: 0 };
                const sel = contents.window.getSelection();
                window.AnnotationManager.activeSelectedText = sel ? sel.toString().trim() : '';
                if (!window.AnnotationManager.activeSelectedText) return;

                const rangeRect = (sel && sel.rangeCount > 0) ? sel.getRangeAt(0).getBoundingClientRect() : null;
                const popWidth = 240;
                const x = Math.max(12, Math.min(window.innerWidth - popWidth - 12, iframeRect.left + (rangeRect ? rangeRect.left + rangeRect.width / 2 - popWidth / 2 : 100)));
                const y = Math.max(60, iframeRect.top + (rangeRect ? rangeRect.top - 48 : 100));

                dismissAllPopovers();
                const selPop = document.getElementById('selection-popover');
                const noteBox = document.getElementById('pop-note-container');
                const noteInput = document.getElementById('pop-note-text');
                if (selPop) {
                    selPop.style.left = `${x}px`;
                    selPop.style.top = `${y}px`;
                    selPop.style.display = 'flex';
                    if (noteBox) noteBox.style.display = 'none';
                    if (noteInput) noteInput.value = '';
                }
            } catch (err) {}
        });

        // Instant Spine / Lazy CFI Restoration (Non-blocking)
        book.ready.then(() => {
            if (isRestoring && !initialCfi && initialPage > 1 && totalPages > 1 && book.spine && book.spine.length) {
                const fraction = Math.max(0, Math.min(1, (initialPage - 1) / (totalPages - 1)));
                const spineIdx = Math.min(book.spine.length - 1, Math.floor(fraction * book.spine.length));
                const item = book.spine.get(spineIdx);
                if (item && item.href) {
                    rendition.display(item.href).catch(() => {});
                }
            }

            // Generate precise CFI locations asynchronously during idle time without blocking UI
            const generateLocationsAsync = () => {
                if (book && book.locations) {
                    book.locations.generate(1600).catch(() => {});
                }
            };
            if ('requestIdleCallback' in window) {
                window.requestIdleCallback(generateLocationsAsync, { timeout: 3000 });
            } else {
                setTimeout(generateLocationsAsync, 1000);
            }
        }).catch(() => {});

        // Relocation & Progress Telemetry
        rendition.on('relocated', (location) => {
            if (!location || !location.start) return;
            const curCfi = location.start.cfi;

            let pct = 0;
            if (book.locations && book.locations.length()) {
                pct = book.locations.percentageFromCfi(curCfi);
            } else if (book.spine && book.spine.length) {
                pct = (location.start.index || 0) / Math.max(1, book.spine.length);
            }
            pct = Math.max(0, Math.min(1, pct));

            const curPage = Math.max(1, Math.min(totalPages, Math.round(pct * (totalPages - 1)) + 1));
            const pctInt = Math.round(pct * 100);

            ProgressSync.updateHud(curPage, totalPages, pctInt, curCfi);

            if (isRestoring) {
                isRestoring = false;
                lastNotifiedCfi = curCfi;
                lastNotifiedPage = curPage;
                return;
            }

            if (curCfi === lastNotifiedCfi && curPage === lastNotifiedPage) return;

            lastNotifiedCfi = curCfi;
            lastNotifiedPage = curPage;

            ProgressSync.scheduleSave({
                book_id: bookId,
                user_id: userId,
                current_page: curPage,
                total_pages: totalPages,
                progress_percent: Math.round(pct * 1000) / 10,
                cfi: curCfi,
                status: (curPage >= totalPages && totalPages > 1) ? 'completed' : 'reading',
                client_timestamp: Date.now() / 1000
            });
        });

        const nextBtn = document.getElementById('next');
        const prevBtn = document.getElementById('prev');
        if (nextBtn) nextBtn.addEventListener("click", () => rendition.next());
        if (prevBtn) prevBtn.addEventListener("click", () => rendition.prev());

        rendition.hooks.content.register((contents) => {
            contents.document.addEventListener("keydown", handleKeyDown);
            contents.document.addEventListener("click", () => dismissAllPopovers());
        });

    } catch (e) {
        console.error("[EPUB Engine] Error:", e);
        if (errorDiv) {
            errorDiv.style.display = 'block';
            errorDiv.innerText = "Fatal Reader Error: " + e.message;
        }
    }
})();