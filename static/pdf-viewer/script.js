/**
 * =========================================================================
 * LIBRE PDF READER ENGINE (Modular & High-Performance)
 * PDF.js Virtualized Canvas Rendering, Text Layer, Telemetry & Annotations
 * =========================================================================
 */

(function() {
    'use strict';

    if (typeof pdfjsLib !== 'undefined') {
        pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    }

    // -------------------------------------------------------------------------
    // 1. CONFIGURATION & STATE INITIALIZATION
    // -------------------------------------------------------------------------
    const urlParams = new URLSearchParams(window.location.search);
    const fileUrl = urlParams.get('file');
    const bookId = urlParams.get('book_id') || '';
    const userId = urlParams.get('user_id') || 'guest';
    const initialPage = Math.max(1, parseInt(urlParams.get('page') || '1', 10));
    const paramTotal = parseInt(urlParams.get('total') || '0', 10);

    const DOM = {
        viewerContainer: document.getElementById('viewer-container'),
        pdfViewer: document.getElementById('pdf-viewer'),
        errorDiv: document.getElementById('error-msg'),
        pageInfo: document.getElementById('page-info'),
        pageNumInput: document.getElementById('page-num-input'),
        pageCountDisplay: document.getElementById('page-count-display'),
        loaderDiv: document.getElementById('initial-loader'),
        appearanceToggle: document.getElementById('appearance-toggle'),
        appearancePopover: document.getElementById('appearance-popover'),
        themeLabel: document.getElementById('theme-label'),
        fullscreenBtn: document.getElementById('fullscreen-btn'),
        zoomInBtn: document.getElementById('zoom-in'),
        zoomOutBtn: document.getElementById('zoom-out'),
        zoomResetBtn: document.getElementById('zoom-reset'),
        prevBtn: document.getElementById('prev'),
        nextBtn: document.getElementById('next'),
        selectionPopover: document.getElementById('selection-popover'),
        popNoteContainer: document.getElementById('pop-note-container'),
        popNoteText: document.getElementById('pop-note-text'),
        popNoteSave: document.getElementById('pop-note-save'),
        popAddNoteBtn: document.getElementById('pop-add-note-btn'),
        popCopyBtn: document.getElementById('pop-copy-btn'),
        popAskTarsBtn: document.getElementById('pop-ask-tars-btn'),
        aiExplainerCard: document.getElementById('ai-explainer-card'),
        aiCardBody: document.getElementById('ai-card-body'),
        aiCardClose: document.getElementById('ai-card-close'),
        aiAttachNoteBtn: document.getElementById('ai-attach-note-btn'),
        aiOpenChatBtn: document.getElementById('ai-open-chat-btn'),
        highlightPopover: document.getElementById('highlight-popover'),
        hlEditNoteText: document.getElementById('hl-edit-note-text'),
        hlSaveNoteBtn: document.getElementById('hl-save-note-btn'),
        hlDeleteBtn: document.getElementById('hl-delete-btn'),
        annotationsDrawer: document.getElementById('annotations-drawer'),
        drawerToggleBtn: document.getElementById('annotations-drawer-toggle'),
        drawerCloseBtn: document.getElementById('drawer-close-btn'),
        drawerBadge: document.getElementById('annotations-badge'),
        drawerCount: document.getElementById('drawer-count'),
        drawerCards: document.getElementById('drawer-cards'),
        drawerSearch: document.getElementById('drawer-search'),
        drawerExportBtn: document.getElementById('drawer-export-btn'),
        readerToast: document.getElementById('reader-toast')
    };

    if (!fileUrl) {
        if (DOM.loaderDiv) DOM.loaderDiv.style.display = 'none';
        if (DOM.errorDiv) {
            DOM.errorDiv.style.display = 'block';
            DOM.errorDiv.innerText = "Error: No PDF document specified in query parameters.";
        }
        return;
    }

    let pdfDoc = null;
    let totalPages = paramTotal > 0 ? paramTotal : 1;
    let currentPage = initialPage;
    let lastNotifiedPage = initialPage;
    let currentScale = 1.25;
    let renderedPages = new Set();
    let pageContainers = [];
    let saveDebounceTimer = null;
    let pendingSavePayload = null;
    let toastTimer = null;

    // -------------------------------------------------------------------------
    // 2. THEME & CONTRAST MANAGER
    // -------------------------------------------------------------------------
    const ThemeManager = {
        currentTheme: localStorage.getItem('libre_reader_theme') || 'light',

        applyTheme(theme, save = true) {
            this.currentTheme = theme;
            document.body.setAttribute('data-theme', theme);
            if (DOM.themeLabel) {
                DOM.themeLabel.innerText = theme.charAt(0).toUpperCase() + theme.slice(1);
            }

            document.querySelectorAll('.theme-swatch').forEach(btn => {
                btn.classList.toggle('active', btn.getAttribute('data-theme') === theme);
            });

            if (save) {
                localStorage.setItem('libre_reader_theme', theme);
                this.notifyParent();
            }
        },

        cycleTheme() {
            const themes = ['light', 'sepia', 'dark', 'black'];
            const nextIdx = (themes.indexOf(this.currentTheme) + 1) % themes.length;
            this.applyTheme(themes[nextIdx], true);
        },

        notifyParent() {
            try {
                window.parent.postMessage({
                    type: 'LIBRE_READER_THEME_CHANGE',
                    theme: this.currentTheme
                }, '*');
            } catch(e) {}
        }
    };

    ThemeManager.applyTheme(ThemeManager.currentTheme, false);

    // -------------------------------------------------------------------------
    // 3. READING PROGRESS & TELEMETRY
    // -------------------------------------------------------------------------
    const ProgressSync = {
        calculatePercentage(page, total) {
            if (total <= 1) return 100.0;
            return Math.max(0.0, Math.min(100.0, Math.round(((page - 1) / (total - 1)) * 1000) / 10));
        },

        updateHud(page, total) {
            const pct = this.calculatePercentage(page, total);
            if (DOM.pageInfo) DOM.pageInfo.innerText = `Page ${page} of ${total} (${pct}%)`;
            if (DOM.pageNumInput) DOM.pageNumInput.value = page;
            if (DOM.pageCountDisplay) DOM.pageCountDisplay.innerText = `of ${total}`;

            try {
                window.parent.postMessage({
                    type: 'LIBRE_READER_PROGRESS',
                    book_id: bookId,
                    current_page: page,
                    total_pages: total,
                    percentage: pct,
                    theme: ThemeManager.currentTheme
                }, '*');
            } catch (err) {}
        },

        scheduleSave(payload) {
            pendingSavePayload = {
                ...payload,
                theme: ThemeManager.currentTheme
            };
            if (saveDebounceTimer) clearTimeout(saveDebounceTimer);
            saveDebounceTimer = setTimeout(() => {
                this.persistReadingProgress(pendingSavePayload);
            }, 500);
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
                console.error("[PDF Engine] Progress sync network error:", err);
            }
        },

        flushPendingSave() {
            if (!pendingSavePayload) return;
            const payloadString = JSON.stringify(pendingSavePayload);
            if (navigator.sendBeacon) {
                navigator.sendBeacon('/api/progress/sync', new Blob([payloadString], { type: 'application/json' }));
            } else {
                fetch('/api/progress/sync', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: payloadString,
                    keepalive: true
                });
            }
            pendingSavePayload = null;
        }
    };

    window.addEventListener('beforeunload', () => ProgressSync.flushPendingSave());
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') ProgressSync.flushPendingSave();
    });

    // -------------------------------------------------------------------------
    // 4. TOAST & POPOVER UTILITIES
    // -------------------------------------------------------------------------
    function showToast(msg) {
        if (!DOM.readerToast) return;
        DOM.readerToast.innerText = msg;
        DOM.readerToast.classList.add('show');
        if (toastTimer) clearTimeout(toastTimer);
        toastTimer = setTimeout(() => {
            DOM.readerToast.classList.remove('show');
        }, 2400);
    }

    function escapeHtml(text) {
        if (!text) return '';
        return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function dismissAllPopovers() {
        if (DOM.selectionPopover) DOM.selectionPopover.style.display = 'none';
        if (DOM.popNoteContainer) DOM.popNoteContainer.style.display = 'none';
        if (DOM.highlightPopover) DOM.highlightPopover.style.display = 'none';
        if (DOM.aiExplainerCard) DOM.aiExplainerCard.style.display = 'none';
    }

    // -------------------------------------------------------------------------
    // 5. ANNOTATIONS & STUDY HIGHLIGHTS ENGINE
    // -------------------------------------------------------------------------
    const AnnotationManager = {
        annotations: [],
        activeHighlight: null,
        activeSelection: null,
        activePopoverColor: "yellow",
        currentFilter: 'all',
        currentSearch: '',

        async fetchAnnotations() {
            try {
                const res = await fetch(`/api/annotations/${encodeURIComponent(bookId)}?user_id=${encodeURIComponent(userId)}`);
                const data = await res.json();
                if (res.ok && data.annotations) {
                    this.annotations = data.annotations;
                    this.updateDrawerUI();
                    this.renderAllVisibleHighlights();
                }
            } catch(e) {
                console.error("[PDF Engine] Error fetching annotations:", e);
            }
        },

        renderPageHighlights(pageNum, layerDiv) {
            if (!layerDiv) return;
            layerDiv.innerHTML = '';
            const pageAnns = this.annotations.filter(a => (a.page_number === pageNum));

            pageAnns.forEach(ann => {
                let rects = [];
                try {
                    if (ann.cfi_range) {
                        const parsed = JSON.parse(ann.cfi_range);
                        if (Array.isArray(parsed)) rects = parsed;
                    }
                } catch(e) {}

                rects.forEach(r => {
                    const el = document.createElement('div');
                    el.className = `pdf-highlight-rect pdf-hl-${ann.color || 'yellow'}`;
                    el.style.left = `${(r.xNorm * 100).toFixed(3)}%`;
                    el.style.top = `${(r.yNorm * 100).toFixed(3)}%`;
                    el.style.width = `${(r.wNorm * 100).toFixed(3)}%`;
                    el.style.height = `${(r.hNorm * 100).toFixed(3)}%`;
                    el.title = ann.note ? `Note: ${ann.note}` : 'Highlight';
                    el.addEventListener('click', (e) => this.onHighlightClicked(e, ann));
                    layerDiv.appendChild(el);
                });
            });
        },

        renderAllVisibleHighlights() {
            document.querySelectorAll('.annotation-layer').forEach(layer => {
                const pNum = parseInt(layer.id.replace('annotation-layer-', ''), 10);
                if (pNum) this.renderPageHighlights(pNum, layer);
            });
        },

        async createAnnotation(color, note = "") {
            if (!this.activeSelection || !this.activeSelection.text) return;
            const sel = this.activeSelection;
            const payload = {
                book_id: bookId,
                user_id: userId,
                selected_text: sel.text,
                color: color || "yellow",
                cfi_range: JSON.stringify(sel.rectsNorm),
                page_number: sel.pageNum,
                note: note
            };

            try {
                const res = await fetch('/api/annotations/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (res.ok && data.annotation) {
                    this.annotations.unshift(data.annotation);
                    this.updateDrawerUI();
                    const layer = document.getElementById(`annotation-layer-${sel.pageNum}`);
                    if (layer) this.renderPageHighlights(sel.pageNum, layer);
                    dismissAllPopovers();
                    showToast(note ? "Highlight with note saved!" : "Highlight saved!");
                    window.getSelection()?.removeAllRanges();
                } else {
                    showToast("Failed to save highlight.");
                }
            } catch(e) {
                showToast("Error saving highlight.");
            }
        },

        onHighlightClicked(e, ann) {
            e.stopPropagation();
            this.activeHighlight = ann;
            const x = Math.max(16, Math.min(window.innerWidth - 260, e.clientX - 100));
            const y = Math.max(60, e.clientY - 60);

            dismissAllPopovers();
            if (DOM.highlightPopover) {
                DOM.highlightPopover.style.left = `${x}px`;
                DOM.highlightPopover.style.top = `${y}px`;
                DOM.highlightPopover.style.display = 'flex';
                if (DOM.hlEditNoteText) DOM.hlEditNoteText.value = ann.note || '';
            }
        },

        async updateAnnotation(annId, updates) {
            if (!annId) return;
            try {
                const res = await fetch(`/api/annotations/${encodeURIComponent(annId)}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(updates)
                });
                const data = await res.json();
                if (res.ok && data.annotation) {
                    const idx = this.annotations.findIndex(a => a.id === annId);
                    if (idx !== -1) {
                        this.annotations[idx] = data.annotation;
                        const pNum = data.annotation.page_number;
                        const layer = document.getElementById(`annotation-layer-${pNum}`);
                        if (layer) this.renderPageHighlights(pNum, layer);
                    }
                    this.updateDrawerUI();
                    dismissAllPopovers();
                    showToast("Annotation updated!");
                }
            } catch(e) {}
        },

        async deleteAnnotation(annId) {
            if (!annId) return;
            try {
                const res = await fetch(`/api/annotations/${encodeURIComponent(annId)}?user_id=${encodeURIComponent(userId)}`, {
                    method: 'DELETE'
                });
                if (res.ok) {
                    const target = this.annotations.find(a => a.id === annId);
                    this.annotations = this.annotations.filter(a => a.id !== annId);
                    if (target) {
                        const layer = document.getElementById(`annotation-layer-${target.page_number}`);
                        if (layer) this.renderPageHighlights(target.page_number, layer);
                    }
                    this.updateDrawerUI();
                    dismissAllPopovers();
                    showToast("Highlight deleted.");
                }
            } catch(e) {}
        },

        updateDrawerUI() {
            if (DOM.drawerBadge) {
                DOM.drawerBadge.innerText = this.annotations.length;
                DOM.drawerBadge.style.display = this.annotations.length > 0 ? 'inline-block' : 'none';
            }
            if (DOM.drawerCount) DOM.drawerCount.innerText = this.annotations.length;
            if (!DOM.drawerCards) return;

            const filtered = this.annotations.filter(ann => {
                const matchColor = (this.currentFilter === 'all') || (ann.color === this.currentFilter);
                const query = this.currentSearch.toLowerCase();
                const matchSearch = !query ||
                    (ann.selected_text && ann.selected_text.toLowerCase().includes(query)) ||
                    (ann.note && ann.note.toLowerCase().includes(query));
                return matchColor && matchSearch;
            });

            if (filtered.length === 0) {
                DOM.drawerCards.innerHTML = `
                    <div style="text-align: center; color: var(--text-controls); padding: 40px 16px; font-size: 13px;">
                        <span style="font-size: 28px; display: block; margin-bottom: 8px;">📖</span>
                        ${this.annotations.length === 0 ? 'No annotations yet.<br>Select any passage in the PDF to highlight or add study notes!' : 'No annotations match your filter.'}
                    </div>
                `;
                return;
            }

            DOM.drawerCards.innerHTML = filtered.map(ann => {
                const colorClass = `ann-card-${ann.color || 'yellow'}`;
                const noteHtml = ann.note ? `<div class="ann-student-note">💭 ${escapeHtml(ann.note)}</div>` : '';
                return `
                    <div class="ann-card ${colorClass}" data-ann-id="${ann.id}" data-page="${ann.page_number || 1}">
                        <div class="ann-card-header">
                            <span style="text-transform: capitalize;">● ${(ann.color || 'yellow')}</span>
                            <span>Page ${ann.page_number || 1}</span>
                        </div>
                        <div class="ann-quote">"${escapeHtml(ann.selected_text || '')}"</div>
                        ${noteHtml}
                        <div class="ann-card-actions">
                            <button class="tool-btn jump-btn" style="padding: 3px 8px; font-size: 11px;">Jump ↗</button>
                            <button class="tool-btn del-btn" style="padding: 3px 8px; font-size: 11px; color: #ef4444;">Delete</button>
                        </div>
                    </div>
                `;
            }).join('');

            // Card Action Listeners
            DOM.drawerCards.querySelectorAll('.ann-card').forEach(card => {
                const annId = card.getAttribute('data-ann-id');
                const pageNum = parseInt(card.getAttribute('data-page'), 10) || 1;

                const jumpBtn = card.querySelector('.jump-btn');
                if (jumpBtn) {
                    jumpBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        PDFRenderer.scrollToPage(pageNum);
                    });
                }

                const delBtn = card.querySelector('.del-btn');
                if (delBtn) {
                    delBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        this.deleteAnnotation(annId);
                    });
                }

                card.addEventListener('click', () => {
                    PDFRenderer.scrollToPage(pageNum);
                });
            });
        },

        toggleDrawer() {
            if (!DOM.annotationsDrawer) return;
            const isOpen = DOM.annotationsDrawer.classList.contains('open');
            DOM.annotationsDrawer.classList.toggle('open', !isOpen);
            if (!isOpen) dismissAllPopovers();
        }
    };

    // -------------------------------------------------------------------------
    // 6. TARS SOCRATIC AI EXPLAINER
    // -------------------------------------------------------------------------
    const TarsExplainer = {
        lastExplainedText: "",
        lastExplanationResult: "",

        async trigger(text) {
            if (!text) return;
            this.lastExplainedText = text;
            const popLeft = DOM.selectionPopover ? DOM.selectionPopover.style.left : "20px";
            const popTop = DOM.selectionPopover ? DOM.selectionPopover.style.top : "80px";
            dismissAllPopovers();

            if (DOM.aiExplainerCard) {
                DOM.aiExplainerCard.style.left = popLeft;
                DOM.aiExplainerCard.style.top = popTop;
                DOM.aiExplainerCard.style.display = 'flex';
                if (DOM.aiCardBody) {
                    DOM.aiCardBody.innerHTML = `
                        <div style="display: flex; align-items: center; gap: 8px; padding: 6px 0; color: var(--text-controls);">
                            <div style="width: 14px; height: 14px; border: 2px solid var(--accent-color); border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
                            <span>TARS is consulting knowledge archive...</span>
                        </div>
                    `;
                }
                if (DOM.aiAttachNoteBtn) DOM.aiAttachNoteBtn.style.display = 'none';
            }

            try {
                const res = await fetch('/api/annotations/explain', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ passage_text: text, book_id: bookId })
                });
                const data = await res.json();
                this.lastExplanationResult = data.explanation || "No explanation provided.";
                if (DOM.aiCardBody) {
                    DOM.aiCardBody.innerHTML = `
                        <div style="font-style: italic; margin-bottom: 6px; color: var(--text-controls); font-size: 11px;">"${escapeHtml(text.length > 80 ? text.substring(0, 80) + '...' : text)}"</div>
                        <div>${escapeHtml(this.lastExplanationResult)}</div>
                    `;
                }
                if (DOM.aiAttachNoteBtn) DOM.aiAttachNoteBtn.style.display = 'inline-block';
            } catch(e) {
                if (DOM.aiCardBody) DOM.aiCardBody.innerText = "TARS explanation unavailable at this time.";
            }
        }
    };

    // -------------------------------------------------------------------------
    // 7. VIRTUALIZED PDF RENDERER & INTERSECTION OBSERVER
    // -------------------------------------------------------------------------
    const PDFRenderer = {
        renderObserver: null,
        scrollDebounceTimer: null,

        scrollToPage(pageNum, smooth = true) {
            const targetContainer = document.getElementById(`page-container-${pageNum}`);
            if (targetContainer && DOM.viewerContainer) {
                const offset = targetContainer.offsetTop - 20;
                DOM.viewerContainer.scrollTo({
                    top: Math.max(0, offset),
                    behavior: smooth ? 'smooth' : 'auto'
                });
                this.onActivePageChanged(pageNum);
            }
        },

        onActivePageChanged(pageNum) {
            if (pageNum < 1 || pageNum > totalPages) return;
            currentPage = pageNum;
            ProgressSync.updateHud(currentPage, totalPages);

            document.querySelectorAll('.page-container').forEach(c => {
                const num = parseInt(c.getAttribute('data-page-number'), 10);
                c.classList.toggle('active-page', num === currentPage);
            });

            if (pageNum === lastNotifiedPage) return;
            lastNotifiedPage = pageNum;

            const pct = ProgressSync.calculatePercentage(pageNum, totalPages);
            ProgressSync.scheduleSave({
                book_id: bookId,
                user_id: userId,
                current_page: pageNum,
                total_pages: totalPages,
                progress_percent: pct,
                status: (pageNum >= totalPages && totalPages > 1) ? 'completed' : 'reading',
                client_timestamp: Date.now() / 1000
            });
        },

        zoomIn() {
            currentScale = Math.min(3.0, currentScale + 0.25);
            this.rebuildLayout();
        },

        zoomOut() {
            currentScale = Math.max(0.5, currentScale - 0.25);
            this.rebuildLayout();
        },

        fitToWidth() {
            if (!pageContainers.length || !pdfDoc) return;
            pdfDoc.getPage(1).then(page => {
                const viewport = page.getViewport({ scale: 1.0 });
                const containerWidth = DOM.viewerContainer.clientWidth - 48;
                currentScale = Math.max(0.5, containerWidth / viewport.width);
                this.rebuildLayout();
            });
        },

        async renderPageCanvas(pageNum, container) {
            if (renderedPages.has(pageNum)) return;
            renderedPages.add(pageNum);

            try {
                const page = await pdfDoc.getPage(pageNum);
                const viewport = page.getViewport({ scale: currentScale });
                const outputScale = window.devicePixelRatio || 1;

                container.innerHTML = '';
                container.style.width = `${Math.floor(viewport.width)}px`;
                container.style.height = `${Math.floor(viewport.height)}px`;

                const canvas = document.createElement('canvas');
                const context = canvas.getContext('2d');

                canvas.width = Math.floor(viewport.width * outputScale);
                canvas.height = Math.floor(viewport.height * outputScale);
                canvas.style.width = `${Math.floor(viewport.width)}px`;
                canvas.style.height = `${Math.floor(viewport.height)}px`;
                container.appendChild(canvas);

                const transform = outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : null;

                await page.render({
                    canvasContext: context,
                    viewport: viewport,
                    transform: transform
                }).promise;

                // PDF.js Text Layer for Selectable Text
                try {
                    const textContent = await page.getTextContent();
                    const textLayerDiv = document.createElement('div');
                    textLayerDiv.className = 'textLayer';
                    textLayerDiv.style.width = `${Math.floor(viewport.width)}px`;
                    textLayerDiv.style.height = `${Math.floor(viewport.height)}px`;
                    textLayerDiv.style.setProperty('--scale-factor', viewport.scale);
                    container.appendChild(textLayerDiv);

                    await pdfjsLib.renderTextLayer({
                        textContentSource: textContent,
                        container: textLayerDiv,
                        viewport: viewport,
                        textDivs: []
                    }).promise;
                } catch(tErr) {}

                // Persistent Annotations Layer
                const annLayer = document.createElement('div');
                annLayer.className = 'annotation-layer';
                annLayer.id = `annotation-layer-${pageNum}`;
                container.appendChild(annLayer);
                AnnotationManager.renderPageHighlights(pageNum, annLayer);

            } catch (err) {
                console.error(`[PDF Engine] Error rendering page ${pageNum}:`, err);
            }
        },

        setupObservers() {
            if (this.renderObserver) this.renderObserver.disconnect();

            this.renderObserver = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    const pageNum = parseInt(entry.target.getAttribute('data-page-number'), 10);
                    if (entry.isIntersecting) {
                        this.renderPageCanvas(pageNum, entry.target);
                    }
                });
            }, {
                root: DOM.viewerContainer,
                rootMargin: '300px 0px 300px 0px'
            });

            pageContainers.forEach(container => {
                this.renderObserver.observe(container);
            });

            DOM.viewerContainer.addEventListener('scroll', () => {
                if (this.scrollDebounceTimer) cancelAnimationFrame(this.scrollDebounceTimer);
                this.scrollDebounceTimer = requestAnimationFrame(() => this.checkActivePageFromScroll());
            }, { passive: true });
        },

        checkActivePageFromScroll() {
            if (!pageContainers.length) return;
            const containerRect = DOM.viewerContainer.getBoundingClientRect();
            const viewportCenter = containerRect.top + containerRect.height / 3;

            let bestPage = currentPage;
            let minDistance = Infinity;

            pageContainers.forEach(container => {
                const rect = container.getBoundingClientRect();
                const dist = Math.abs(rect.top - viewportCenter);
                if (dist < minDistance) {
                    minDistance = dist;
                    bestPage = parseInt(container.getAttribute('data-page-number'), 10);
                }
            });

            if (bestPage !== currentPage) {
                this.onActivePageChanged(bestPage);
            }
        },

        rebuildLayout() {
            renderedPages.clear();
            DOM.pdfViewer.innerHTML = '';
            pageContainers = [];

            if (!pdfDoc) return;

            pdfDoc.getPage(1).then(firstPage => {
                const viewport = firstPage.getViewport({ scale: currentScale });
                const estWidth = Math.floor(viewport.width);
                const estHeight = Math.floor(viewport.height);

                for (let i = 1; i <= totalPages; i++) {
                    const container = document.createElement('div');
                    container.className = 'page-container';
                    container.id = `page-container-${i}`;
                    container.setAttribute('data-page-number', i);
                    container.style.width = `${estWidth}px`;
                    container.style.minHeight = `${estHeight}px`;

                    const skeleton = document.createElement('div');
                    skeleton.className = 'page-loading-skeleton';
                    skeleton.style.width = `${estWidth}px`;
                    skeleton.style.height = `${estHeight}px`;
                    skeleton.innerText = `Page ${i}`;
                    container.appendChild(skeleton);

                    DOM.pdfViewer.appendChild(container);
                    pageContainers.push(container);
                }

                this.setupObservers();
                this.scrollToPage(currentPage, false);
            });
        }
    };

    // -------------------------------------------------------------------------
    // 8. TEXT SELECTION & ANNOTATION LISTENER
    // -------------------------------------------------------------------------
    document.addEventListener('selectionchange', () => {
        const sel = window.getSelection();
        if (!sel || sel.isCollapsed || !sel.rangeCount) return;

        const range = sel.getRangeAt(0);
        const text = sel.toString().trim();
        if (!text || text.length < 2) return;

        let node = range.commonAncestorContainer;
        while (node && !node.classList?.contains('page-container')) {
            node = node.parentNode;
        }
        if (!node) return;

        const pageNum = parseInt(node.getAttribute('data-page-number'), 10);
        if (!pageNum) return;

        const pageRect = node.getBoundingClientRect();
        const clientRects = Array.from(range.getClientRects());
        if (!clientRects.length) return;

        const rectsNorm = clientRects.map(r => ({
            xNorm: (r.left - pageRect.left) / pageRect.width,
            yNorm: (r.top - pageRect.top) / pageRect.height,
            wNorm: r.width / pageRect.width,
            hNorm: r.height / pageRect.height
        }));

        AnnotationManager.activeSelection = {
            text: text,
            pageNum: pageNum,
            rectsNorm: rectsNorm
        };

        const firstRect = clientRects[0];
        const popWidth = 240;
        const x = Math.max(12, Math.min(window.innerWidth - popWidth - 12, firstRect.left + firstRect.width / 2 - popWidth / 2));
        const y = Math.max(60, firstRect.top - 52);

        dismissAllPopovers();
        if (DOM.selectionPopover) {
            DOM.selectionPopover.style.left = `${x}px`;
            DOM.selectionPopover.style.top = `${y}px`;
            DOM.selectionPopover.style.display = 'flex';
            if (DOM.popNoteContainer) DOM.popNoteContainer.style.display = 'none';
            if (DOM.popNoteText) DOM.popNoteText.value = '';
        }
    });

    // -------------------------------------------------------------------------
    // 9. EVENT LISTENERS & SHORTCUTS
    // -------------------------------------------------------------------------
    function handleKeyDown(e) {
        if (e.target && ['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return;

        if (e.key === "ArrowLeft" || e.key === "PageUp" || e.key === "j") {
            if (currentPage > 1) PDFRenderer.scrollToPage(currentPage - 1);
            e.preventDefault();
        } else if (e.key === "ArrowRight" || e.key === "PageDown" || e.key === "k") {
            if (currentPage < totalPages) PDFRenderer.scrollToPage(currentPage + 1);
            e.preventDefault();
        } else if (e.key === "t" || e.key === "T") {
            ThemeManager.cycleTheme();
            e.preventDefault();
        } else if (e.key === "h" || e.key === "H") {
            AnnotationManager.toggleDrawer();
            e.preventDefault();
        } else if (e.key === "+" || e.key === "=") {
            PDFRenderer.zoomIn();
            e.preventDefault();
        } else if (e.key === "-" || e.key === "_") {
            PDFRenderer.zoomOut();
            e.preventDefault();
        } else if (e.key === "f" || e.key === "F") {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch(() => {});
            } else {
                document.exitFullscreen().catch(() => {});
            }
            e.preventDefault();
        } else if (e.key === "Escape") {
            dismissAllPopovers();
            if (DOM.appearancePopover) DOM.appearancePopover.style.display = 'none';
            if (DOM.annotationsDrawer) DOM.annotationsDrawer.classList.remove('open');
        }
    }

    document.addEventListener("keydown", handleKeyDown);

    // Zoom Buttons
    if (DOM.zoomInBtn) DOM.zoomInBtn.addEventListener('click', () => PDFRenderer.zoomIn());
    if (DOM.zoomOutBtn) DOM.zoomOutBtn.addEventListener('click', () => PDFRenderer.zoomOut());
    if (DOM.zoomResetBtn) DOM.zoomResetBtn.addEventListener('click', () => PDFRenderer.fitToWidth());

    // Navigation Buttons
    if (DOM.prevBtn) DOM.prevBtn.addEventListener('click', () => {
        if (currentPage > 1) PDFRenderer.scrollToPage(currentPage - 1);
    });
    if (DOM.nextBtn) DOM.nextBtn.addEventListener('click', () => {
        if (currentPage < totalPages) PDFRenderer.scrollToPage(currentPage + 1);
    });

    if (DOM.pageNumInput) {
        DOM.pageNumInput.addEventListener('change', (e) => {
            const requested = parseInt(e.target.value, 10);
            if (requested >= 1 && requested <= totalPages) {
                PDFRenderer.scrollToPage(requested);
            } else {
                e.target.value = currentPage;
            }
        });
    }

    // Appearance Popover Listeners
    if (DOM.appearanceToggle && DOM.appearancePopover) {
        DOM.appearanceToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            const isVisible = DOM.appearancePopover.style.display === 'flex';
            DOM.appearancePopover.style.display = isVisible ? 'none' : 'flex';
        });

        document.addEventListener('click', (e) => {
            if (DOM.appearancePopover && !DOM.appearancePopover.contains(e.target) && e.target !== DOM.appearanceToggle) {
                DOM.appearancePopover.style.display = 'none';
            }
        });
    }

    document.querySelectorAll('.theme-swatch').forEach(btn => {
        btn.addEventListener('click', () => {
            ThemeManager.applyTheme(btn.getAttribute('data-theme'), true);
        });
    });

    const popZoomIn = document.getElementById('pop-zoom-in');
    const popZoomOut = document.getElementById('pop-zoom-out');
    const popZoomFit = document.getElementById('pop-zoom-fit');
    if (popZoomIn) popZoomIn.addEventListener('click', () => PDFRenderer.zoomIn());
    if (popZoomOut) popZoomOut.addEventListener('click', () => PDFRenderer.zoomOut());
    if (popZoomFit) popZoomFit.addEventListener('click', () => PDFRenderer.fitToWidth());

    if (DOM.fullscreenBtn) {
        DOM.fullscreenBtn.addEventListener('click', () => {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch(() => {});
            } else {
                document.exitFullscreen().catch(() => {});
            }
        });
    }

    // Selection Popover Listeners
    document.querySelectorAll('#selection-popover .hl-swatch').forEach(swatch => {
        swatch.addEventListener('click', (e) => {
            e.stopPropagation();
            const color = swatch.getAttribute('data-color') || 'yellow';
            AnnotationManager.activePopoverColor = color;
            AnnotationManager.createAnnotation(color, "");
        });
    });

    if (DOM.popAddNoteBtn) {
        DOM.popAddNoteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (!DOM.popNoteContainer) return;
            const isOpen = DOM.popNoteContainer.style.display === 'flex';
            DOM.popNoteContainer.style.display = isOpen ? 'none' : 'flex';
            if (!isOpen && DOM.popNoteText) DOM.popNoteText.focus();
        });
    }

    if (DOM.popNoteSave) {
        DOM.popNoteSave.addEventListener('click', (e) => {
            e.stopPropagation();
            const note = DOM.popNoteText ? DOM.popNoteText.value.trim() : "";
            AnnotationManager.createAnnotation(AnnotationManager.activePopoverColor || "yellow", note);
        });
    }

    if (DOM.popCopyBtn) {
        DOM.popCopyBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (AnnotationManager.activeSelection?.text) {
                navigator.clipboard.writeText(`"${AnnotationManager.activeSelection.text}" (Libre-Library)`).then(() => {
                    showToast("Quote copied to clipboard!");
                    dismissAllPopovers();
                }).catch(() => {
                    showToast("Clipboard access denied.");
                });
            }
        });
    }

    if (DOM.popAskTarsBtn) {
        DOM.popAskTarsBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (AnnotationManager.activeSelection?.text) {
                TarsExplainer.trigger(AnnotationManager.activeSelection.text);
            }
        });
    }

    if (DOM.aiCardClose) {
        DOM.aiCardClose.addEventListener('click', (e) => {
            e.stopPropagation();
            if (DOM.aiExplainerCard) DOM.aiExplainerCard.style.display = 'none';
        });
    }

    if (DOM.aiAttachNoteBtn) {
        DOM.aiAttachNoteBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (TarsExplainer.lastExplainedText && TarsExplainer.lastExplanationResult) {
                await AnnotationManager.createAnnotation("blue", "TARS AI: " + TarsExplainer.lastExplanationResult);
                dismissAllPopovers();
            }
        });
    }

    if (DOM.aiOpenChatBtn) {
        DOM.aiOpenChatBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const prompt = `Can you explain this excerpt in detail: "${TarsExplainer.lastExplainedText}"`;
            try {
                window.parent.postMessage({ type: 'OPEN_TARS_CHAT', message: prompt }, '*');
            } catch(e) {}
            window.open(`/chat?prompt=${encodeURIComponent(prompt)}`, '_blank');
        });
    }

    document.querySelectorAll('#highlight-popover .hl-swatch').forEach(swatch => {
        swatch.addEventListener('click', (e) => {
            e.stopPropagation();
            const newColor = swatch.getAttribute('data-update-color');
            if (AnnotationManager.activeHighlight && newColor) {
                AnnotationManager.updateAnnotation(AnnotationManager.activeHighlight.id, { color: newColor });
            }
        });
    });

    if (DOM.hlSaveNoteBtn) {
        DOM.hlSaveNoteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const note = DOM.hlEditNoteText ? DOM.hlEditNoteText.value.trim() : "";
            if (AnnotationManager.activeHighlight) {
                AnnotationManager.updateAnnotation(AnnotationManager.activeHighlight.id, { note: note });
            }
        });
    }

    if (DOM.hlDeleteBtn) {
        DOM.hlDeleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (AnnotationManager.activeHighlight) {
                AnnotationManager.deleteAnnotation(AnnotationManager.activeHighlight.id);
            }
        });
    }

    if (DOM.drawerToggleBtn) {
        DOM.drawerToggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            AnnotationManager.toggleDrawer();
        });
    }

    if (DOM.drawerCloseBtn) {
        DOM.drawerCloseBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (DOM.annotationsDrawer) DOM.annotationsDrawer.classList.remove('open');
        });
    }

    document.querySelectorAll('.drawer-filter-bar .filter-pill').forEach(pill => {
        pill.addEventListener('click', () => {
            document.querySelectorAll('.drawer-filter-bar .filter-pill').forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            AnnotationManager.currentFilter = pill.getAttribute('data-filter') || 'all';
            AnnotationManager.updateDrawerUI();
        });
    });

    if (DOM.drawerSearch) {
        DOM.drawerSearch.addEventListener('input', (e) => {
            AnnotationManager.currentSearch = e.target.value.trim();
            AnnotationManager.updateDrawerUI();
        });
    }

    if (DOM.drawerExportBtn) {
        DOM.drawerExportBtn.addEventListener('click', () => {
            window.location.href = `/api/annotations/${encodeURIComponent(bookId)}/export?user_id=${encodeURIComponent(userId)}`;
            showToast("Study guide download initiated!");
        });
    }

    document.addEventListener('click', (e) => {
        if (DOM.selectionPopover && !DOM.selectionPopover.contains(e.target) && e.target !== DOM.selectionPopover) {
            DOM.selectionPopover.style.display = 'none';
        }
        if (DOM.highlightPopover && !DOM.highlightPopover.contains(e.target) && e.target !== DOM.highlightPopover) {
            DOM.highlightPopover.style.display = 'none';
        }
        if (DOM.aiExplainerCard && !DOM.aiExplainerCard.contains(e.target) && e.target !== DOM.aiExplainerCard) {
            DOM.aiExplainerCard.style.display = 'none';
        }
    });

    // Parent Window Commands
    window.addEventListener('message', function(event) {
        if (!event.data) return;
        if (event.data.type === 'READER_NAVIGATE') {
            if (event.data.action === 'next' && currentPage < totalPages) {
                PDFRenderer.scrollToPage(currentPage + 1);
            } else if (event.data.action === 'prev' && currentPage > 1) {
                PDFRenderer.scrollToPage(currentPage - 1);
            }
        } else if (event.data.type === 'SET_THEME' && event.data.theme) {
            ThemeManager.applyTheme(event.data.theme, true);
        }
    });

    // -------------------------------------------------------------------------
    // 10. PDF.JS DOCUMENT LOADING LIFECYCLE
    // -------------------------------------------------------------------------
    const loadingTask = pdfjsLib.getDocument({
        url: fileUrl,
        cMapUrl: 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/cmaps/',
        cMapPacked: true
    });

    loadingTask.promise.then(async function(loadedDoc) {
        pdfDoc = loadedDoc;
        totalPages = pdfDoc.numPages;

        if (DOM.loaderDiv) DOM.loaderDiv.style.display = 'none';
        ProgressSync.updateHud(currentPage, totalPages);

        const firstPage = await pdfDoc.getPage(1);
        const viewport = firstPage.getViewport({ scale: 1.0 });
        const containerWidth = DOM.viewerContainer.clientWidth - 48;
        if (containerWidth > 0 && viewport.width > 0) {
            currentScale = Math.max(0.6, Math.min(2.0, containerWidth / viewport.width));
        }

        PDFRenderer.rebuildLayout();
        AnnotationManager.fetchAnnotations();

        if (initialPage > 1) {
            setTimeout(() => {
                PDFRenderer.scrollToPage(initialPage, false);
            }, 100);
        } else {
            PDFRenderer.onActivePageChanged(1);
        }
    }).catch(function(error) {
        console.error("[PDF Engine] Error loading PDF:", error);
        if (DOM.loaderDiv) DOM.loaderDiv.style.display = 'none';
        if (DOM.errorDiv) {
            DOM.errorDiv.style.display = 'block';
            DOM.errorDiv.innerText = "Error loading PDF document: " + error.message;
        }
    });

})();
