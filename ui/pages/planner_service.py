import os
import uuid
import tempfile
import asyncio
import re
import gc
import traceback
import time
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple

from nicegui import run
from core.database.mongo_manager import mongo_db
from core.ai_engine.llm_engine import tars_engine
from core.utils.text_extractor import extract_text_from_file

class FlashcardService:
    """
    Optimized Flashcard & Study Deck Generator:
    - Native document extraction (PDF, DOCX, PPTX, TXT, EPUB)
    - Fast, targeted AI inference via TarsEngine
    - Safe async file parsing
    """
    CHUNK_SIZE = 3500 

    async def get_deck(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves deck from MongoDB."""
        return await mongo_db.get_deck(task_id)

    async def delete_deck(self, task_id: str) -> bool:
        """Deletes deck from MongoDB."""
        await mongo_db.delete_deck(task_id)
        return True

    async def delete_deck_by_task(self, task_id: str) -> bool:
        """Alias for delete_deck."""
        return await self.delete_deck(task_id)

    async def generate_deck(self, task_id: str, file_obj: Any, on_status=None) -> Tuple[bool, str]:
        temp_path = None
        start_time = time.time()
        try:
            if on_status:
                on_status("Reading document...")

            # 1. Resolve filename and content bytes universally
            filename = "document.txt"
            content_bytes = None

            # Handle NiceGUI UploadEventArguments (e.file is FileUpload)
            if hasattr(file_obj, 'file'):
                sub_file = file_obj.file
                filename = getattr(sub_file, 'name', None) or getattr(file_obj, 'name', 'document.txt')
                if hasattr(sub_file, 'read'):
                    res = sub_file.read()
                    content_bytes = await res if asyncio.iscoroutine(res) else res
            elif hasattr(file_obj, 'name'):
                filename = file_obj.name

            if content_bytes is None:
                if hasattr(file_obj, 'read'):
                    res = file_obj.read()
                    content_bytes = await res if asyncio.iscoroutine(res) else res
                elif hasattr(file_obj, 'content'):
                    c = file_obj.content
                    if isinstance(c, bytes):
                        content_bytes = c
                    elif hasattr(c, 'read'):
                        res = c.read()
                        content_bytes = await res if asyncio.iscoroutine(res) else res
                elif isinstance(file_obj, bytes):
                    content_bytes = file_obj
                elif isinstance(file_obj, (str, Path)) and os.path.exists(str(file_obj)):
                    filename = Path(file_obj).name
                    with open(file_obj, 'rb') as f:
                        content_bytes = f.read()

            if not content_bytes:
                return False, "Could not read any data from the provided document."

            _, ext = os.path.splitext(filename)
            ext = ext.lower() or '.txt'

            # 2. Write temp file and close immediately (Windows file locking safe)
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(content_bytes)
                temp_path = tmp.name

            if on_status:
                on_status("Extracting document text...")

            # 3. Extract text using native extractor
            raw_text = await run.io_bound(extract_text_from_file, temp_path)
            if not raw_text or len(raw_text.strip()) < 40: 
                return False, "The file contains no readable text or is empty."

            if on_status:
                on_status("Generating flashcards with TARS AI...")

            # 4. Smart Chunking & Targeted Flashcard Generation
            chunks = self._smart_chunk_text(raw_text, self.CHUNK_SIZE)
            if not chunks:
                return False, "Could not segment document content for study cards."

            # Process up to 2 key chunks (avoids 10+ minute inference hangs)
            selected_chunks = chunks[:2]
            all_cards = []
            cards_per_chunk = "15" if len(selected_chunks) > 1 else "20"

            for i, chunk in enumerate(selected_chunks):
                gc.collect()
                chunk_context = f"--- SECTION {i+1} ---\n{chunk}"
                chunk_cards = await self._query_tars_cards(chunk_context, cards_per_chunk)
                if chunk_cards:
                    all_cards.extend(chunk_cards)

            if not all_cards: 
                return False, "TARS AI could not generate cards from this text. Please ensure the local AI model is loaded."

            if on_status:
                on_status("Saving flashcard deck...")

            # 5. Save to MongoDB
            await mongo_db.save_deck(task_id, filename, all_cards)
            
            total_time = time.time() - start_time
            return True, f"Success! {len(all_cards)} cards generated in {total_time:.1f}s."

        except Exception as e:
            traceback.print_exc()
            return False, f"Generation error: {str(e)}"
        finally:
            if temp_path and os.path.exists(temp_path):
                try: os.unlink(temp_path)
                except Exception: pass

    def _smart_chunk_text(self, text: str, max_chars: int) -> List[str]:
        """Splits text efficiently while preserving sentence boundaries."""
        text = " ".join(text.split())
        chunks = []
        current_chunk = ""
        
        for sentence in text.split('. '):
            sentence = sentence + ". "
            if len(current_chunk) + len(sentence) < max_chars:
                current_chunk += sentence
            else:
                if current_chunk: chunks.append(current_chunk)
                current_chunk = sentence
        
        if current_chunk: chunks.append(current_chunk)
        return chunks

    async def _query_tars_cards(self, context_text: str, quantity: str = "15") -> List[Dict]:
        """Queries TARS with strict format prompts and robust parser."""
        prompt = (
            f"Create {quantity} flashcards based on the text below.\n"
            "STRICT FORMAT: Question ||| Answer\n"
            "EXAMPLE:\n"
            "What is CPU? ||| Central Processing Unit\n"
            "What is RAM? ||| Random Access Memory\n\n"
            f"TEXT:\n{context_text[:3500]}\n\n"
            "FLASHCARDS:"
        )

        # Thread-safe async inference with concise token limit for rapid completion
        raw_text = await tars_engine.create_completion(
            prompt=prompt,
            max_tokens=1000,
            temperature=0.3,
            stop=["TEXT:", "Example:", "---", "\n\n\n"]
        )

        if not raw_text:
            return []

        cards = []
        lines = raw_text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line: continue

            # Strategy A: "|||" delimiter
            if "|||" in line:
                parts = line.split("|||")
                if len(parts) >= 2:
                    q = re.sub(r'^[\d\.\-\)\s]+|^(Q:|Question:)\s*', '', parts[0].strip(), flags=re.IGNORECASE)
                    a = re.sub(r'^(A:|Answer:)\s*', '', parts[1].strip(), flags=re.IGNORECASE)
                    if len(q) > 1 and len(a) > 1:
                        cards.append({"q": q, "a": a})
                        continue

            # Strategy B: Fallback Q:... A:...
            qa_match = re.match(r'(?:Q|Question)[:\.\-]\s*(.*?)\s*(?:A|Answer)[:\.\-]\s*(.*)', line, re.IGNORECASE)
            if qa_match:
                cards.append({"q": qa_match.group(1).strip(), "a": qa_match.group(2).strip()})

        return cards

planner_service = FlashcardService()