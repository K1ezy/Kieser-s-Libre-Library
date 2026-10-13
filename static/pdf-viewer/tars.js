/**
 * Libre PDF Reader - TARS Socratic Explainer
 * Integrates passage analysis with TARS AI and enables one-click escalation to chat.
 */
(function() {
    'use strict';

    function escapeHtml(text) {
        if (!text) return '';
        return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    const TarsExplainer = {
        lastExplainedText: '',
        lastExplanationResult: '',
        context: null, // { bookId, showToast, dismissAllPopovers }

        async trigger(text, popLeft = '20px', popTop = '80px') {
            if (!text) return;
            this.lastExplainedText = text;
            const card = document.getElementById('ai-explainer-card');
            const cardBody = document.getElementById('ai-card-body');
            const attachBtn = document.getElementById('ai-attach-note-btn');

            if (this.context && this.context.dismissAllPopovers) {
                this.context.dismissAllPopovers();
            }

            if (card) {
                card.style.left = popLeft;
                card.style.top = popTop;
                card.style.display = 'flex';
                if (cardBody) {
                    cardBody.innerHTML = `
                        <div style="display: flex; align-items: center; gap: 8px; padding: 6px 0; color: var(--text-controls);">
                            <div style="width: 14px; height: 14px; border: 2px solid var(--accent-color); border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
                            <span>TARS is consulting knowledge archive...</span>
                        </div>
                    `;
                }
                if (attachBtn) attachBtn.style.display = 'none';
            }

            try {
                const res = await fetch('/api/annotations/explain', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ passage_text: text, book_id: this.context.bookId })
                });
                const data = await res.json();
                this.lastExplanationResult = data.explanation || "No explanation provided.";
                if (cardBody) {
                    cardBody.innerHTML = `
                        <div style="font-style: italic; margin-bottom: 6px; color: var(--text-controls); font-size: 11px;">"${escapeHtml(text.length > 80 ? text.substring(0, 80) + '...' : text)}"</div>
                        <div>${escapeHtml(this.lastExplanationResult)}</div>
                    `;
                }
                if (attachBtn) attachBtn.style.display = 'inline-block';
            } catch(e) {
                if (cardBody) cardBody.innerText = "TARS explanation unavailable at this time.";
            }
        },

        init(ctx) {
            this.context = ctx;

            const askTarsBtn = document.getElementById('pop-ask-tars-btn');
            if (askTarsBtn) {
                askTarsBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const text = window.AnnotationManager && window.AnnotationManager.activeSelectionData ? window.AnnotationManager.activeSelectionData.text : '';
                    const pop = document.getElementById('selection-popover');
                    const left = pop ? pop.style.left : '20px';
                    const top = pop ? pop.style.top : '80px';
                    this.trigger(text, left, top);
                });
            }

            const cardClose = document.getElementById('ai-card-close');
            const card = document.getElementById('ai-explainer-card');
            if (cardClose && card) {
                cardClose.addEventListener('click', (e) => {
                    e.stopPropagation();
                    card.style.display = 'none';
                });
            }

            const attachNoteBtn = document.getElementById('ai-attach-note-btn');
            if (attachNoteBtn) {
                attachNoteBtn.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    if (this.lastExplainedText && this.lastExplanationResult && window.AnnotationManager) {
                        await window.AnnotationManager.createAnnotation("blue", "TARS AI: " + this.lastExplanationResult);
                        ctx.dismissAllPopovers();
                    }
                });
            }

            const openChatBtn = document.getElementById('ai-open-chat-btn');
            if (openChatBtn) {
                openChatBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const prompt = `Can you explain this excerpt from the PDF: "${this.lastExplainedText}"`;
                    try {
                        window.parent.postMessage({ type: 'OPEN_TARS_CHAT', message: prompt }, '*');
                    } catch(e) {}
                    window.open(`/chat?prompt=${encodeURIComponent(prompt)}`, '_blank');
                });
            }
        }
    };

    window.TarsExplainer = TarsExplainer;
})();
