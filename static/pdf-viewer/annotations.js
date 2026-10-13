/**
 * Libre PDF Reader - Annotations & Highlights Manager
 * Virtualized multi-page highlight overlay with percentage normalization,
 * sticky study notes, search drawer, and Markdown export.
 */
(function() {
    'use strict';

    function escapeHtml(text) {
        if (!text) return '';
        return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    const AnnotationManager = {
        annotations: [],
        activeSelectionData: null, // { text, pageNumber, rects: [{xNorm, yNorm, wNorm, hNorm}] }
        activePopoverColor: 'yellow',
        activeHighlight: null,
        currentFilter: 'all',
        currentSearch: '',
        context: null, // { bookId, userId, showToast, dismissAllPopovers, scrollToPage }

        getColorHex(color) {
            const map = { green: '#bbf7d0', blue: '#bfdbfe', pink: '#fbcfe8' };
            return map[(color || 'yellow').toLowerCase()] || '#fef08a';
        },

        async fetchAnnotations() {
            const { bookId, userId } = this.context;
            if (!bookId) return;
            try {
                const res = await fetch(`/api/annotations/${encodeURIComponent(bookId)}?user_id=${encodeURIComponent(userId)}`);
                const data = await res.json();
                if (res.ok && data.annotations) {
                    this.annotations = data.annotations;
                    this.updateDrawerUI();
                    this.refreshAllPageHighlights();
                }
            } catch(e) {
                console.error("[PDF Annotations] Fetch error:", e);
            }
        },

        renderHighlightsForPage(pageNumber, pageContainer) {
            if (!pageContainer) return;
            const annLayer = pageContainer.querySelector('.page-annotations-layer');
            if (!annLayer) return;

            annLayer.innerHTML = '';
            const pageAnns = this.annotations.filter(a => (a.page_number === pageNumber || a.page === pageNumber));

            pageAnns.forEach(ann => {
                const rects = ann.rects || ann.boxes || [];
                rects.forEach(r => {
                    const hl = document.createElement('div');
                    hl.className = `pdf-highlight-rect pdf-hl-${ann.color || 'yellow'}`;
                    hl.style.left = `${(r.xNorm * 100).toFixed(3)}%`;
                    hl.style.top = `${(r.yNorm * 100).toFixed(3)}%`;
                    hl.style.width = `${(r.wNorm * 100).toFixed(3)}%`;
                    hl.style.height = `${(r.hNorm * 100).toFixed(3)}%`;
                    hl.setAttribute('data-ann-id', ann.id);

                    hl.addEventListener('click', (e) => this.onHighlightClicked(e, ann, hl));
                    annLayer.appendChild(hl);
                });
            });
        },

        refreshAllPageHighlights() {
            document.querySelectorAll('.page-container').forEach(container => {
                const pageNum = parseInt(container.getAttribute('data-page-number'), 10);
                if (pageNum) this.renderHighlightsForPage(pageNum, container);
            });
        },

        async createAnnotation(color, note = "") {
            const { bookId, userId, showToast, dismissAllPopovers } = this.context;
            if (!this.activeSelectionData || !this.activeSelectionData.text) return;

            const payload = {
                book_id: bookId,
                user_id: userId,
                selected_text: this.activeSelectionData.text,
                color: color || "yellow",
                page_number: this.activeSelectionData.pageNumber || 1,
                rects: this.activeSelectionData.rects || [],
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
                    this.refreshAllPageHighlights();
                    dismissAllPopovers();
                    showToast(note ? "Highlight with note saved!" : "Highlight saved!");
                } else {
                    showToast("Failed to save highlight.");
                }
            } catch(e) {
                showToast("Error saving highlight.");
            }
        },

        onHighlightClicked(e, ann, hlDiv) {
            e.stopPropagation();
            this.activeHighlight = ann;
            const { dismissAllPopovers } = this.context;

            const rect = hlDiv.getBoundingClientRect();
            const x = Math.max(12, Math.min(window.innerWidth - 260, rect.left + rect.width / 2 - 120));
            const y = Math.max(60, rect.top - 60);

            dismissAllPopovers();
            const popover = document.getElementById('highlight-popover');
            const noteText = document.getElementById('hl-edit-note-text');
            if (popover) {
                popover.style.left = `${x}px`;
                popover.style.top = `${y}px`;
                popover.style.display = 'flex';
                if (noteText) noteText.value = ann.note || '';
            }
        },

        async updateAnnotation(annId, updates) {
            const { showToast, dismissAllPopovers } = this.context;
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
                        this.refreshAllPageHighlights();
                    }
                    this.updateDrawerUI();
                    dismissAllPopovers();
                    showToast("Annotation updated!");
                }
            } catch(e) {}
        },

        async deleteAnnotation(annId) {
            const { userId, showToast, dismissAllPopovers } = this.context;
            if (!annId) return;
            try {
                const res = await fetch(`/api/annotations/${encodeURIComponent(annId)}?user_id=${encodeURIComponent(userId)}`, {
                    method: 'DELETE'
                });
                if (res.ok) {
                    this.annotations = this.annotations.filter(a => a.id !== annId);
                    this.updateDrawerUI();
                    this.refreshAllPageHighlights();
                    dismissAllPopovers();
                    showToast("Highlight deleted.");
                }
            } catch(e) {}
        },

        updateDrawerUI() {
            const badge = document.getElementById('annotations-badge');
            const count = document.getElementById('drawer-count');
            const cardsContainer = document.getElementById('drawer-cards');

            if (badge) {
                badge.innerText = this.annotations.length;
                badge.style.display = this.annotations.length > 0 ? 'inline-block' : 'none';
            }
            if (count) count.innerText = this.annotations.length;
            if (!cardsContainer) return;

            const filtered = this.annotations.filter(ann => {
                const matchColor = (this.currentFilter === 'all') || (ann.color === this.currentFilter);
                const query = this.currentSearch.toLowerCase();
                const matchSearch = !query ||
                    (ann.selected_text && ann.selected_text.toLowerCase().includes(query)) ||
                    (ann.note && ann.note.toLowerCase().includes(query));
                return matchColor && matchSearch;
            });

            if (filtered.length === 0) {
                cardsContainer.innerHTML = `
                    <div style="text-align: center; color: var(--text-controls); padding: 40px 16px; font-size: 13px;">
                        <span style="font-size: 28px; display: block; margin-bottom: 8px;">📑</span>
                        ${this.annotations.length === 0 ? 'No annotations yet.<br>Select any text in the PDF to highlight or attach notes!' : 'No annotations match your filter.'}
                    </div>
                `;
                return;
            }

            cardsContainer.innerHTML = filtered.map(ann => {
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

            const { scrollToPage } = this.context;
            cardsContainer.querySelectorAll('.ann-card').forEach(card => {
                const annId = card.getAttribute('data-ann-id');
                const page = parseInt(card.getAttribute('data-page') || '1', 10);

                const jumpBtn = card.querySelector('.jump-btn');
                if (jumpBtn) {
                    jumpBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        if (scrollToPage) scrollToPage(page);
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
                    if (scrollToPage) scrollToPage(page);
                });
            });
        },

        toggleDrawer() {
            const drawer = document.getElementById('annotations-drawer');
            if (!drawer) return;
            const isOpen = drawer.classList.contains('open');
            drawer.classList.toggle('open', !isOpen);
            if (!isOpen) this.context.dismissAllPopovers();
        },

        init(ctx) {
            this.context = ctx;

            // Highlight Swatches
            document.querySelectorAll('#selection-popover .hl-swatch').forEach(swatch => {
                swatch.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const color = swatch.getAttribute('data-color') || 'yellow';
                    this.activePopoverColor = color;
                    this.createAnnotation(color, "");
                });
            });

            // Note Toggle & Save
            const popAddNote = document.getElementById('pop-add-note-btn');
            const noteContainer = document.getElementById('pop-note-container');
            const noteText = document.getElementById('pop-note-text');
            if (popAddNote && noteContainer) {
                popAddNote.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const isOpen = noteContainer.style.display === 'flex';
                    noteContainer.style.display = isOpen ? 'none' : 'flex';
                    if (!isOpen && noteText) noteText.focus();
                });
            }

            const popNoteSave = document.getElementById('pop-note-save');
            if (popNoteSave) {
                popNoteSave.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const note = noteText ? noteText.value.trim() : "";
                    this.createAnnotation(this.activePopoverColor || "yellow", note);
                });
            }

            // Copy Citation
            const popCopy = document.getElementById('pop-copy-btn');
            if (popCopy) {
                popCopy.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const text = this.activeSelectionData ? this.activeSelectionData.text : '';
                    if (text) {
                        navigator.clipboard.writeText(`"${text}" (Libre-Library PDF)`).then(() => {
                            ctx.showToast("Quote copied to clipboard!");
                            ctx.dismissAllPopovers();
                        }).catch(() => {
                            ctx.showToast("Clipboard access denied.");
                        });
                    }
                });
            }

            // Update Highlight Note & Color
            document.querySelectorAll('#highlight-popover .hl-swatch').forEach(swatch => {
                swatch.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const newColor = swatch.getAttribute('data-update-color');
                    if (this.activeHighlight && newColor) {
                        this.updateAnnotation(this.activeHighlight.id, { color: newColor });
                    }
                });
            });

            const hlSaveNote = document.getElementById('hl-save-note-btn');
            const hlEditNoteText = document.getElementById('hl-edit-note-text');
            if (hlSaveNote) {
                hlSaveNote.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const note = hlEditNoteText ? hlEditNoteText.value.trim() : "";
                    if (this.activeHighlight) this.updateAnnotation(this.activeHighlight.id, { note });
                });
            }

            const hlDeleteBtn = document.getElementById('hl-delete-btn');
            if (hlDeleteBtn) {
                hlDeleteBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (this.activeHighlight) this.deleteAnnotation(this.activeHighlight.id);
                });
            }

            // Drawer Toggles & Search
            const drawerToggle = document.getElementById('annotations-drawer-toggle');
            if (drawerToggle) drawerToggle.addEventListener('click', (e) => { e.stopPropagation(); this.toggleDrawer(); });

            const drawerClose = document.getElementById('drawer-close-btn');
            const drawer = document.getElementById('annotations-drawer');
            if (drawerClose && drawer) drawerClose.addEventListener('click', (e) => { e.stopPropagation(); drawer.classList.remove('open'); });

            document.querySelectorAll('.drawer-filter-bar .filter-pill').forEach(pill => {
                pill.addEventListener('click', () => {
                    document.querySelectorAll('.drawer-filter-bar .filter-pill').forEach(p => p.classList.remove('active'));
                    pill.classList.add('active');
                    this.currentFilter = pill.getAttribute('data-filter') || 'all';
                    this.updateDrawerUI();
                });
            });

            const searchInput = document.getElementById('drawer-search');
            if (searchInput) {
                searchInput.addEventListener('input', (e) => {
                    this.currentSearch = e.target.value.trim();
                    this.updateDrawerUI();
                });
            }

            const exportBtn = document.getElementById('drawer-export-btn');
            if (exportBtn) {
                exportBtn.addEventListener('click', () => {
                    window.location.href = `/api/annotations/${encodeURIComponent(ctx.bookId)}/export?user_id=${encodeURIComponent(ctx.userId)}`;
                    ctx.showToast("Study guide download initiated!");
                });
            }
        }
    };

    window.AnnotationManager = AnnotationManager;
})();
