/**
 * Libre PDF Reader - Core Lifecycle & Virtualized Rendering Engine
 * Handles PDF.js worker setup, lazy page rendering via IntersectionObserver,
 * selectable text layers with normalized highlight bounding boxes, and zoom controls.
 */
(function() {
    'use strict';

    if (typeof pdfjsLib !== 'undefined') {
        pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    }

    // 1. Initialization Parameters
    const urlParams = new URLSearchParams(window.location.search);
    const fileUrl = urlParams.get('file');
    const bookId = urlParams.get('book_id') || '';
    const userId = urlParams.get('user_id') || 'guest';
    const initialPage = Math.max(1, parseInt(urlParams.get('page') || '1', 10));
    const paramTotal = parseInt(urlParams.get('total') || '0', 10);

    const viewerContainer = document.getElementById('viewer-container');
    const pdfViewer = document.getElementById('pdf-viewer');
    const errorDiv = document.getElementById('error-msg');
    const pageInfo = document.getElementById('page-info');
    const pageNumInput = document.getElementById('page-num-input');
    const pageCountDisplay = document.getElementById('page-count-display');
    const loaderDiv = document.getElementById('initial-loader');
    const toastDiv = document.getElementById('reader-toast');
    let toastTimer = null;

    if (!fileUrl) {
        if (loaderDiv) loaderDiv.style.display = 'none';
        if (errorDiv) {
            errorDiv.style.display = 'block';
            errorDiv.innerText = "Error: No PDF document specified in query parameters.";
        }
        return;
    }

    let pdfDoc = null;
    let totalPages = paramTotal > 0 ? paramTotal : 1;
    let currentPage = initialPage;
    let lastNotifiedPage = initialPage;
    let currentScale = 1.25;
    const renderedPages = new Set();
    const pageContainers = [];
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
        calculatePercentage(page, total) {
            if (total <= 1) return 100.0;
            return Math.max(0.0, Math.min(100.0, Math.round(((page - 1) / (total - 1)) * 1000) / 10));
        },

        updateHud(page, total) {
            const pct = this.calculatePercentage(page, total);
            if (pageInfo) pageInfo.innerText = `Page ${page} of ${total} (${pct}%)`;
            if (pageNumInput) pageNumInput.value = page;
            if (pageCountDisplay) pageCountDisplay.innerText = `of ${total}`;

            try {
                window.parent.postMessage({
                    type: 'LIBRE_READER_PROGRESS',
                    book_id: bookId,
                    current_page: page,
                    total_pages: total,
                    percentage: pct,
                    theme: window.ThemeManager.currentTheme
                }, '*');
            } catch(e) {}
        },

        scheduleSave(payload) {
            pendingSavePayload = {
                ...payload,
                theme: window.ThemeManager.currentTheme
            };
            if (saveDebounceTimer) clearTimeout(saveDebounceTimer);
            saveDebounceTimer = setTimeout(() => this.persistProgress(pendingSavePayload), 500);
        },

        async persistProgress(payload) {
            if (!payload || !payload.book_id) return;
            try {
                await fetch('/api/progress/sync', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
            } catch(e) {
                console.error("[PDF Progress] Persist error:", e);
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

    // 4. Zoom & Viewport Scaling
    function setScale(newScale) {
        currentScale = Math.max(0.6, Math.min(3.0, newScale));
        renderedPages.clear();

        const viewerRect = viewerContainer ? viewerContainer.getBoundingClientRect() : { top: 0, bottom: window.innerHeight };

        pageContainers.forEach(container => {
            const pageNum = parseInt(container.getAttribute('data-page-number'), 10);
            const rect = container.getBoundingClientRect();
            const isVisible = (rect.bottom >= viewerRect.top - 250 && rect.top <= viewerRect.bottom + 250);

            if (isVisible) {
                renderPage(pageNum, container);
            } else {
                const canvas = container.querySelector('.pdf-canvas');
                if (canvas && canvas._renderTask) {
                    try { canvas._renderTask.cancel(); } catch(e) {}
                    canvas._renderTask = null;
                }
            }
        });
    }

    function zoomIn() { setScale(currentScale + 0.2); }
    function zoomOut() { setScale(currentScale - 0.2); }
    function zoomReset() {
        if (!viewerContainer) return;
        const width = viewerContainer.clientWidth - 48;
        if (width > 300) setScale(Math.max(0.6, Math.min(2.0, width / 700)));
        else setScale(1.0);
    }

    // 5. Page Navigation
    function scrollToPage(pageNum) {
        pageNum = Math.max(1, Math.min(totalPages, pageNum));
        const target = pageContainers[pageNum - 1];
        if (target) {
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            currentPage = pageNum;
            ProgressSync.updateHud(pageNum, totalPages);
        }
    }

    function nextPage() { scrollToPage(currentPage + 1); }
    function prevPage() { scrollToPage(currentPage - 1); }

    // 6. Virtualized Page Rendering Pipeline
    function createPageSkeleton(pageNum, estWidth, estHeight) {
        const container = document.createElement('div');
        container.className = 'page-container';
        container.setAttribute('data-page-number', pageNum);
        container.id = `pdf-page-${pageNum}`;
        if (estWidth && estHeight) {
            container.style.width = `${estWidth}px`;
            container.style.height = `${estHeight}px`;
            container.style.minHeight = `${estHeight}px`;
        }

        const canvas = document.createElement('canvas');
        canvas.className = 'pdf-canvas';

        const textLayer = document.createElement('div');
        textLayer.className = 'textLayer';

        const annLayer = document.createElement('div');
        annLayer.className = 'page-annotations-layer';

        container.appendChild(canvas);
        container.appendChild(textLayer);
        container.appendChild(annLayer);
        pageContainers.push(container);

        bindTextSelectionOnContainer(container, pageNum);
        return container;
    }

    async function renderPage(pageNum, container) {
        if (!pdfDoc) return;
        const canvas = container.querySelector('.pdf-canvas');
        const textLayer = container.querySelector('.textLayer');
        if (!canvas) return;

        // Cancel previous active render task on this canvas if any
        if (canvas._renderTask) {
            try { canvas._renderTask.cancel(); } catch(e) {}
            canvas._renderTask = null;
        }

        try {
            const page = await pdfDoc.getPage(pageNum);
            const viewport = page.getViewport({ scale: currentScale });

            canvas.height = viewport.height;
            canvas.width = viewport.width;
            container.style.width = `${viewport.width}px`;
            container.style.height = `${viewport.height}px`;

            const ctx = canvas.getContext('2d');
            const renderTask = page.render({ canvasContext: ctx, viewport });
            canvas._renderTask = renderTask;
            await renderTask.promise;
            canvas._renderTask = null;

            if (textLayer) {
                textLayer.innerHTML = '';
                textLayer.style.width = `${viewport.width}px`;
                textLayer.style.height = `${viewport.height}px`;

                const textContent = await page.getTextContent();
                await pdfjsLib.renderTextLayer({
                    textContent,
                    container: textLayer,
                    viewport,
                    textDivs: []
                }).promise;
            }

            renderedPages.add(pageNum);
            if (window.AnnotationManager) {
                window.AnnotationManager.renderHighlightsForPage(pageNum, container);
            }
        } catch(e) {
            if (e && e.name !== 'RenderingCancelledException') {
                console.error(`[PDF Render] Error page ${pageNum}:`, e);
            }
        }
    }

    function bindTextSelectionOnContainer(container, pageNum) {
        container.addEventListener('mouseup', () => {
            const sel = window.getSelection();
            if (!sel || sel.isCollapsed) return;

            const selectedText = sel.toString().trim();
            if (!selectedText) return;

            const range = sel.getRangeAt(0);
            const containerRect = container.getBoundingClientRect();
            const clientRects = range.getClientRects();
            if (!clientRects || clientRects.length === 0) return;

            const normRects = [];
            for (let i = 0; i < clientRects.length; i++) {
                const r = clientRects[i];
                if (r.width <= 1 || r.height <= 1) continue;
                normRects.push({
                    xNorm: Math.max(0, (r.left - containerRect.left) / containerRect.width),
                    yNorm: Math.max(0, (r.top - containerRect.top) / containerRect.height),
                    wNorm: Math.min(1, r.width / containerRect.width),
                    hNorm: Math.min(1, r.height / containerRect.height)
                });
            }

            if (normRects.length === 0) return;

            window.AnnotationManager.activeSelectionData = {
                text: selectedText,
                pageNumber: pageNum,
                rects: normRects
            };

            const lastR = clientRects[0];
            const popWidth = 240;
            const x = Math.max(12, Math.min(window.innerWidth - popWidth - 12, lastR.left + lastR.width / 2 - popWidth / 2));
            const y = Math.max(60, lastR.top - 48);

            dismissAllPopovers();
            const pop = document.getElementById('selection-popover');
            const noteBox = document.getElementById('pop-note-container');
            const noteText = document.getElementById('pop-note-text');
            if (pop) {
                pop.style.left = `${x}px`;
                pop.style.top = `${y}px`;
                pop.style.display = 'flex';
                if (noteBox) noteBox.style.display = 'none';
                if (noteText) noteText.value = '';
            }
        });
    }

    // 7. IntersectionObserver for Virtualized Rendering & HUD Tracking
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const pageNum = parseInt(entry.target.getAttribute('data-page-number'), 10);
            if (entry.isIntersecting) {
                if (!renderedPages.has(pageNum)) {
                    renderPage(pageNum, entry.target);
                }
                if (entry.intersectionRatio > 0.45 && pageNum !== currentPage) {
                    currentPage = pageNum;
                    ProgressSync.updateHud(currentPage, totalPages);

                    if (pageNum !== lastNotifiedPage) {
                        lastNotifiedPage = pageNum;
                        ProgressSync.scheduleSave({
                            book_id: bookId,
                            user_id: userId,
                            current_page: pageNum,
                            total_pages: totalPages,
                            progress_percent: ProgressSync.calculatePercentage(pageNum, totalPages),
                            status: (pageNum >= totalPages && totalPages > 1) ? 'completed' : 'reading',
                            client_timestamp: Date.now() / 1000
                        });
                    }
                }
            }
        });
    }, { root: viewerContainer, threshold: [0.1, 0.5] });

    // 8. Keyboard Shortcuts & Global Click Listeners
    function handleKeyDown(e) {
        if (e.target && ['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return;
        if (e.key === "ArrowLeft" || e.key === "PageUp" || e.key === "j") { prevPage(); e.preventDefault(); }
        else if (e.key === "ArrowRight" || e.key === "PageDown" || e.key === "k") { nextPage(); e.preventDefault(); }
        else if (e.key === "+" || e.key === "=") { zoomIn(); e.preventDefault(); }
        else if (e.key === "-" || e.key === "_") { zoomOut(); e.preventDefault(); }
        else if (e.key === "t" || e.key === "T") { window.ThemeManager.cycleTheme(); e.preventDefault(); }
        else if (e.key === "h" || e.key === "H") { window.AnnotationManager.toggleDrawer(); e.preventDefault(); }
        else if (e.key === "Escape") {
            dismissAllPopovers();
            const pop = document.getElementById('appearance-popover');
            const drawer = document.getElementById('annotations-drawer');
            if (pop) pop.style.display = 'none';
            if (drawer) drawer.classList.remove('open');
        }
    }

    document.addEventListener("keydown", handleKeyDown);

    window.addEventListener('message', (e) => {
        if (!e.data) return;
        if (e.data.type === 'READER_NAVIGATE') {
            if (e.data.action === 'next') nextPage();
            else if (e.data.action === 'prev') prevPage();
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

    // 9. Controls Button Binding
    const zoomInBtn = document.getElementById('zoom-in');
    const zoomOutBtn = document.getElementById('zoom-out');
    const zoomResetBtn = document.getElementById('zoom-reset');
    const prevBtn = document.getElementById('prev');
    const nextBtn = document.getElementById('next');

    if (zoomInBtn) zoomInBtn.addEventListener('click', zoomIn);
    if (zoomOutBtn) zoomOutBtn.addEventListener('click', zoomOut);
    if (zoomResetBtn) zoomResetBtn.addEventListener('click', zoomReset);
    if (prevBtn) prevBtn.addEventListener('click', prevPage);
    if (nextBtn) nextBtn.addEventListener('click', nextPage);

    const popZoomIn = document.getElementById('pop-zoom-in');
    const popZoomOut = document.getElementById('pop-zoom-out');
    const popZoomFit = document.getElementById('pop-zoom-fit');
    if (popZoomIn) popZoomIn.addEventListener('click', zoomIn);
    if (popZoomOut) popZoomOut.addEventListener('click', zoomOut);
    if (popZoomFit) popZoomFit.addEventListener('click', zoomReset);

    if (pageNumInput) {
        pageNumInput.addEventListener('change', (e) => {
            const p = parseInt(e.target.value, 10);
            if (!isNaN(p)) scrollToPage(p);
        });
    }

    // 10. Initialize Sub-Modules & Load Document
    window.ThemeManager.init();

    window.AnnotationManager.init({
        bookId,
        userId,
        showToast,
        dismissAllPopovers,
        scrollToPage
    });

    window.TarsExplainer.init({
        bookId,
        showToast,
        dismissAllPopovers
    });

    pdfjsLib.getDocument({ url: fileUrl, cMapUrl: 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/cmaps/', cMapPacked: true })
        .promise
        .then(async doc => {
            pdfDoc = doc;
            totalPages = doc.numPages;
            if (loaderDiv) loaderDiv.style.display = 'none';
            ProgressSync.updateHud(currentPage, totalPages);

            let estWidth = 700;
            let estHeight = 900;
            try {
                const firstPage = await doc.getPage(1);
                const fpViewport = firstPage.getViewport({ scale: currentScale });
                estWidth = fpViewport.width;
                estHeight = fpViewport.height;
            } catch(e) {}

            const fragment = document.createDocumentFragment();
            for (let i = 1; i <= totalPages; i++) {
                const skeleton = createPageSkeleton(i, estWidth, estHeight);
                fragment.appendChild(skeleton);
                observer.observe(skeleton);
            }
            if (pdfViewer) pdfViewer.appendChild(fragment);

            window.AnnotationManager.fetchAnnotations();

            if (initialPage > 1) {
                setTimeout(() => scrollToPage(initialPage), 150);
            }
        })
        .catch(err => {
            console.error("[PDF Engine] Load error:", err);
            if (loaderDiv) loaderDiv.style.display = 'none';
            if (errorDiv) {
                errorDiv.style.display = 'block';
                errorDiv.innerText = "Fatal PDF Error: " + err.message;
            }
        });
})();
