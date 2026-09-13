import logging
import asyncio
import threading
from pathlib import Path
from typing import AsyncGenerator, Optional, Dict, Any, List
from core.config import settings

# Setup Logger
logger = logging.getLogger("TARS_LLM")

# --- CONSTANTS ---
FUNCTIONAL_CONTEXT_LIMIT = 7000 
MAX_OUTPUT_TOKENS = 2048 
MAX_RAG_CHARS = 24000

class TarsEngine:
    """
    Lazy-loaded, thread-safe wrapper around llama-cpp-python for TARS AI.
    Prevents heavy startup freezes by deferring model weight loading until needed.
    """
    def __init__(self):
        self.llm = None
        self._load_lock = threading.Lock()
        self.lock = asyncio.Lock()
        self.context_window = min(settings.CONTEXT_WINDOW, 16384)
        self.model_path = settings.MODEL_DIR / settings.MODEL_FILENAME
        self._is_loaded = False
        logger.info("TARS Engine registered (Lazy Loading Mode).")

    @property
    def is_available(self) -> bool:
        """Returns True if the GGUF model file exists on disk."""
        return self.model_path.exists()

    def ensure_loaded(self) -> bool:
        """
        Thread-safely loads the model into memory/GPU if not already loaded.
        Returns True if model is ready, False otherwise.
        """
        if self._is_loaded and self.llm is not None:
            return True

        with self._load_lock:
            if self._is_loaded and self.llm is not None:
                return True

            if not self.model_path.exists():
                logger.error(f"TARS Model missing at: {self.model_path}")
                return False

            try:
                from llama_cpp import Llama
                logger.info(f"Loading TARS Engine: {settings.MODEL_FILENAME} (CTX: {self.context_window}, GPU_LAYERS: {settings.GPU_LAYERS})...")
                
                # Use configured GPU layers (-1 for full offload, or int like 20)
                gpu_layers = settings.GPU_LAYERS
                
                self.llm = Llama(
                    model_path=str(self.model_path),
                    n_ctx=self.context_window,
                    n_gpu_layers=gpu_layers,
                    n_threads=6,
                    use_mmap=True,
                    use_mlock=False,
                    verbose=False,
                    n_batch=512,
                    chat_format="llama-3"
                )
                self._is_loaded = True
                logger.info("TARS Engine Initialization: COMPLETE")
                return True
            except Exception as e:
                logger.critical(f"TARS Engine FAILED to load model: {e}", exc_info=True)
                self.llm = None
                self._is_loaded = False
                return False

    async def create_completion(
        self,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        stop: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Thread-safe non-streaming completion for tasks like flashcard or plan generation.
        Runs inference in a worker thread to keep the NiceGUI event loop responsive.
        """
        if not await asyncio.to_thread(self.ensure_loaded):
            logger.error("create_completion: Model could not be loaded.")
            return None

        async with self.lock:
            def _infer():
                try:
                    res = self.llm.create_completion(
                        prompt=prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        stop=stop or ["TEXT:", "Example:", "---"]
                    )
                    return res['choices'][0]['text']
                except Exception as ex:
                    logger.error(f"Inference error in create_completion: {ex}", exc_info=True)
                    return None

            return await asyncio.to_thread(_infer)

    async def stream_response(self, messages: list) -> AsyncGenerator[str, None]:
        """
        Async Generator that safely streams chat response with concurrency lock protection.
        """
        if not await asyncio.to_thread(self.ensure_loaded):
            yield "[SYSTEM NOTICE: AI Model is not loaded or missing. Please verify model weights in the models directory.]"
            return

        async with self.lock:
            try:
                # Truncate overly long RAG context to preserve context window
                system_message = messages[0]['content'] if messages else ""
                rag_start = system_message.find("2. **KNOWLEDGE BASE:**\n")
                if rag_start != -1:
                    rag_content_start_index = rag_start + len("2. **KNOWLEDGE BASE:**\n")
                    rag_content = system_message[rag_content_start_index:]
                    if len(rag_content) > MAX_RAG_CHARS:
                        rag_content_truncated = rag_content[:MAX_RAG_CHARS] + "\n... [TRUNCATED]"
                        messages[0]['content'] = system_message[:rag_content_start_index] + rag_content_truncated
                        logger.warning(f"RAG content truncated to {MAX_RAG_CHARS} chars.")

                stream = self.llm.create_chat_completion(
                    messages=messages,
                    stream=True,
                    temperature=0.2,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    stop=["<|eot_id|>", "<|end_of_text|>"]
                )

                def get_next_token():
                    try:
                        return next(stream)
                    except StopIteration:
                        return None

                while True:
                    chunk = await asyncio.to_thread(get_next_token)
                    if chunk is None:
                        break
                    delta = chunk['choices'][0]['delta']
                    if 'content' in delta:
                        yield delta['content']

            except Exception as e:
                logger.error(f"Inference Failure: {e}", exc_info=True)
                yield f"[INFERENCE ERROR: {str(e)}]"

# Singleton instance
tars_engine = TarsEngine()