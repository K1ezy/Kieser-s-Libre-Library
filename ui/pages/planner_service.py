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
    - Native document extraction (PDF, DOCX, PPTX, TXT)
    - Thread-safe AI inference via TarsEngine
    - Hallucination-resistant parsing
    """
    CHUNK_SIZE = 3500 

    async def get_deck(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves deck from MongoDB."""
        return await mongo_db.get_deck(task_id)

    async def delete_deck(self, task_id: str) -> bool:
        """Deletes deck from MongoDB."""
        await mongo_db.delete_deck(task_id)
        return True

    async def generate_deck(self, task_id: str, file_obj: Any) -> Tuple[bool, str]:
        temp_path = None
        start_time = time.time()
        try:
            # 1. Save temp file safely
            filename = getattr(file_obj, 'name', None) or getattr(file_obj, 'filename', None) or f"doc_{uuid.uuid4().hex[:6]}"
            _, ext = os.path.splitext(filename)
            ext = ext.lower() or '.txt'

            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                if hasattr(file_obj, 'read'):
                    content = file_obj.read()
                    if asyncio.iscoroutine(content): content = await content
                    tmp.write(content)
                elif hasattr(file_obj, 'file') and hasattr(file_obj.file, 'read'):
                    content = file_obj.file.read()
                    if asyncio.iscoroutine(content): content = await content
                    tmp.write(content)
                elif isinstance(file_obj, bytes):
                    tmp.write(file_obj)
                else:
                    return False, f"Unsupported file type: {type(file_obj)}"
                temp_path = tmp.name

            # 2. Extract text using unified native extractor
            raw_text = await run.io_bound(extract_text_from_file, temp_path)
            if not raw_text or len(raw_text) < 50: 
                return False, "File is empty or contains no readable text."

            # 3. Smart Chunking
            chunks = self._smart_chunk_text(raw_text, self.CHUNK_SIZE)

            # 4. Generate Cards via TarsEngine
            all_cards = []
            cards_per_chunk = "30" if len(chunks) == 1 else "15"

            for i, chunk in enumerate(chunks):
                gc.collect()
                chunk_context = f"--- TEXT PART {i+1} ---\n{chunk}"
                chunk_cards = await self._query_tars_cards(chunk_context, cards_per_chunk)
                if chunk_cards:
                    all_cards.extend(chunk_cards)
            
            if not all_cards: 
                return False, "AI model produced 0 cards. Please ensure model weights are available."

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

    async def _query_tars_cards(self, context_text: str, quantity: str) -> List[Dict]:
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

        # Thread-safe async inference
        raw_text = await tars_engine.create_completion(
            prompt=prompt,
            max_tokens=2500,
            temperature=0.3,
            stop=["TEXT:", "Example:", "---"]
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