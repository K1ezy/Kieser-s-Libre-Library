import logging
import asyncio
import threading
import json
from pathlib import Path
from typing import AsyncGenerator, Optional, Dict, Any, List
import httpx
from core.config import settings

# Setup Logger
logger = logging.getLogger("TARS_LLM")

# --- CONSTANTS ---
FUNCTIONAL_CONTEXT_LIMIT = 7000 
MAX_OUTPUT_TOKENS = 2048 
MAX_RAG_CHARS = 24000

class TarsEngine:
    """
    Multi-Provider AI Engine for Libre-Library:
    1. Local GGUF (llama-cpp-python) with lazy loading & GPU offloading
    2. Ollama (local or network Ollama API: http://localhost:11434)
    3. OpenAI-Compatible API (OpenAI, DeepSeek, Groq, OpenRouter, LM Studio, vLLM)
    """
    def __init__(self):
        self.provider = getattr(settings, 'AI_PROVIDER', 'local').lower()
        self.ollama_url = getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')
        self.ollama_model = getattr(settings, 'OLLAMA_MODEL', 'llama3.2:latest')
        self.openai_url = getattr(settings, 'OPENAI_API_BASE', 'https://api.openai.com/v1').rstrip('/')
        self.openai_key = getattr(settings, 'OPENAI_API_KEY', '')
        self.openai_model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')

        # Local Llama-cpp state
        self.llm = None
        self._load_lock = threading.Lock()
        self.lock = asyncio.Lock()
        self.context_window = min(settings.CONTEXT_WINDOW, 16384)
        self.model_path = settings.MODEL_DIR / settings.MODEL_FILENAME
        self._is_loaded = False
        self._db_loaded = False

        logger.info(f"TARS Engine initialized (Active Provider: {self.provider.upper()}).")

    async def ensure_db_settings_loaded(self):
        """Loads persistent admin provider configurations from MongoDB on first use."""
        if self._db_loaded:
            return
        try:
            from core.database.mongo_manager import mongo_db
            if mongo_db.db is not None:
                sys_cfg = await mongo_db.get_system_settings()
                if sys_cfg:
                    self.provider = sys_cfg.get("ai_provider", self.provider).lower()
                    self.ollama_url = sys_cfg.get("ollama_url", self.ollama_url).rstrip('/')
                    self.ollama_model = sys_cfg.get("ollama_model", self.ollama_model)
                    self.openai_url = sys_cfg.get("openai_url", self.openai_url).rstrip('/')
                    self.openai_key = sys_cfg.get("openai_key", self.openai_key)
                    self.openai_model = sys_cfg.get("openai_model", self.openai_model)
                    logger.info(f"TARS Engine re-configured from DB (Provider: {self.provider.upper()}).")
                self._db_loaded = True
        except Exception as e:
            logger.debug(f"DB Settings check notice: {e}")

    def configure(self, provider: str, config: Dict[str, Any]):
        """Dynamically updates active provider and endpoint credentials."""
        self.provider = provider.lower()
        if "ollama_url" in config: self.ollama_url = config["ollama_url"].rstrip('/')
        if "ollama_model" in config: self.ollama_model = config["ollama_model"]
        if "openai_url" in config: self.openai_url = config["openai_url"].rstrip('/')
        if "openai_key" in config: self.openai_key = config["openai_key"]
        if "openai_model" in config: self.openai_model = config["openai_model"]
        logger.info(f"TARS Engine dynamically switched to: {self.provider.upper()}")

    @property
    def is_available(self) -> bool:
        """Returns True if the active provider is configured and ready."""
        if self.provider == 'local':
            return self.model_path.exists()
        elif self.provider == 'ollama':
            return bool(self.ollama_url and self.ollama_model)
        elif self.provider == 'openai':
            return bool(self.openai_url and (self.openai_key or "localhost" in self.openai_url or "127.0.0.1" in self.openai_url))
        return False

    @property
    def is_busy(self) -> bool:
        """Returns True if the local model is currently executing inference."""
        return self.lock.locked()

    def ensure_loaded(self) -> bool:

        """
        Thread-safely loads local GGUF weights into memory/GPU if in local mode.
        For Ollama or OpenAI, returns True immediately.
        """
        if self.provider != 'local':
            return True

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
                logger.info(f"Loading Local TARS Engine: {settings.MODEL_FILENAME} (CTX: {self.context_window}, GPU_LAYERS: {settings.GPU_LAYERS})...")
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
                logger.info("Local TARS Engine Initialization: COMPLETE")
                return True
            except Exception as e:
                logger.critical(f"TARS Engine FAILED to load model: {e}", exc_info=True)
                self.llm = None
                self._is_loaded = False
                return False

    async def test_connection(self) -> Dict[str, Any]:
        """Validates network connectivity and model readiness for the active provider."""
        await self.ensure_db_settings_loaded()

        if self.provider == 'local':
            if not self.model_path.exists():
                return {"success": False, "provider": "local", "message": f"GGUF model not found at {self.model_path.name}"}
            ready = await asyncio.to_thread(self.ensure_loaded)
            return {
                "success": ready,
                "provider": "local",
                "model": settings.MODEL_FILENAME,
                "message": "Local GGUF model loaded and operational." if ready else "Failed to load GGUF model into memory."
            }

        elif self.provider == 'ollama':
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(f"{self.ollama_url}/api/tags")
                    if resp.status_code == 200:
                        data = resp.json()
                        models = [m.get('name', '') for m in data.get('models', [])]
                        has_model = any(self.ollama_model in m for m in models)
                        msg = f"Ollama online. Model '{self.ollama_model}' detected." if has_model else f"Ollama online, but model '{self.ollama_model}' not found in installed models: {models[:3]}"
                        return {"success": True, "provider": "ollama", "model": self.ollama_model, "message": msg}
                    return {"success": False, "provider": "ollama", "message": f"Ollama returned HTTP status {resp.status_code}"}
            except Exception as e:
                return {"success": False, "provider": "ollama", "message": f"Cannot connect to Ollama at {self.ollama_url}: {e}"}

        elif self.provider == 'openai':
            try:
                headers = {"Authorization": f"Bearer {self.openai_key}"} if self.openai_key else {}
                async with httpx.AsyncClient(timeout=6.0) as client:
                    # Test simple completion or models endpoint
                    url = f"{self.openai_url}/models"
                    resp = await client.get(url, headers=headers)
                    if resp.status_code in (200, 404):  # Some local servers don't support /models
                        return {"success": True, "provider": "openai", "model": self.openai_model, "message": f"OpenAI-compatible endpoint reachable at {self.openai_url}."}
                    return {"success": False, "provider": "openai", "message": f"Endpoint returned HTTP status {resp.status_code}"}
            except Exception as e:
                return {"success": False, "provider": "openai", "message": f"Cannot connect to API endpoint: {e}"}

        return {"success": False, "provider": self.provider, "message": f"Unknown provider '{self.provider}'"}

    async def create_completion(
        self,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        stop: Optional[List[str]] = None
    ) -> Optional[str]:
        """Thread-safe and async-safe completion across all 3 providers."""
        await self.ensure_db_settings_loaded()

        # 1. Ollama Provider
        if self.provider == 'ollama':
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    payload = {
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": temperature,
                            "num_predict": max_tokens,
                            "stop": stop or ["TEXT:", "Example:", "---"]
                        }
                    }
                    resp = await client.post(f"{self.ollama_url}/api/generate", json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        return data.get("response", "").strip()
                    logger.error(f"Ollama generation failed ({resp.status_code}): {resp.text}")
                    return None
            except Exception as e:
                logger.error(f"Ollama create_completion error: {e}")
                return None

        # 2. OpenAI Compatible Provider
        elif self.provider == 'openai':
            try:
                headers = {"Authorization": f"Bearer {self.openai_key}"} if self.openai_key else {}
                headers["Content-Type"] = "application/json"
                async with httpx.AsyncClient(timeout=60.0) as client:
                    payload = {
                        "model": self.openai_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "stop": stop or ["TEXT:", "Example:", "---"]
                    }
                    resp = await client.post(f"{self.openai_url}/chat/completions", json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        return data["choices"][0]["message"]["content"].strip()
                    logger.error(f"OpenAI completion failed ({resp.status_code}): {resp.text}")
                    return None
            except Exception as e:
                logger.error(f"OpenAI create_completion error: {e}")
                return None

        # 3. Local LLaMA GGUF Provider (Default)
        else:
            if not await asyncio.to_thread(self.ensure_loaded):
                logger.error("create_completion: Local model could not be loaded.")
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

    async def generate_response(
        self,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        stop: Optional[List[str]] = None
    ) -> Optional[str]:
        """Convenience method for direct prompt completion across all AI providers."""
        return await self.create_completion(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop
        )

    async def stream_response(self, messages: list) -> AsyncGenerator[str, None]:
        """Streams chat tokens asynchronously across Local, Ollama, and OpenAI providers."""
        await self.ensure_db_settings_loaded()

        # Clean / truncate context if overly huge
        system_message = messages[0]['content'] if messages else ""
        rag_start = system_message.find("2. **KNOWLEDGE BASE:**\n")
        if rag_start != -1:
            rag_content_start_index = rag_start + len("2. **KNOWLEDGE BASE:**\n")
            rag_content = system_message[rag_content_start_index:]
            if len(rag_content) > MAX_RAG_CHARS:
                rag_content_truncated = rag_content[:MAX_RAG_CHARS] + "\n... [TRUNCATED]"
                messages[0]['content'] = system_message[:rag_content_start_index] + rag_content_truncated

        # 1. Ollama Streaming
        if self.provider == 'ollama':
            try:
                # Convert messages format to Ollama chat
                async with httpx.AsyncClient(timeout=120.0) as client:
                    payload = {
                        "model": self.ollama_model,
                        "messages": messages,
                        "stream": True,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": MAX_OUTPUT_TOKENS
                        }
                    }
                    async with client.stream("POST", f"{self.ollama_url}/api/chat", json=payload) as response:
                        if response.status_code != 200:
                            yield f"[OLLAMA ERROR: Status {response.status_code}]"
                            return
                        async for line in response.aiter_lines():
                            if line and line.strip():
                                try:
                                    chunk_data = json.loads(line)
                                    msg = chunk_data.get("message", {})
                                    content = msg.get("content", "")
                                    if content:
                                        yield content
                                except Exception:
                                    pass
                return
            except Exception as e:
                logger.error(f"Ollama streaming failure: {e}")
                yield f"[OLLAMA CONNECTION ERROR: {str(e)}]"
                return

        # 2. OpenAI / Compatible Streaming
        elif self.provider == 'openai':
            try:
                headers = {"Authorization": f"Bearer {self.openai_key}"} if self.openai_key else {}
                headers["Content-Type"] = "application/json"
                async with httpx.AsyncClient(timeout=120.0) as client:
                    payload = {
                        "model": self.openai_model,
                        "messages": messages,
                        "stream": True,
                        "temperature": 0.3,
                        "max_tokens": MAX_OUTPUT_TOKENS
                    }
                    async with client.stream("POST", f"{self.openai_url}/chat/completions", json=payload, headers=headers) as response:
                        if response.status_code != 200:
                            body = await response.aread()
                            yield f"[API ERROR: Status {response.status_code} - {body.decode('utf-8', 'ignore')}]"
                            return
                        async for line in response.aiter_lines():
                            if line.startswith("data: ") and not line.startswith("data: [DONE]"):
                                raw_json = line[6:].strip()
                                try:
                                    data = json.loads(raw_json)
                                    choices = data.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            yield content
                                except Exception:
                                    pass
                return
            except Exception as e:
                logger.error(f"OpenAI streaming failure: {e}")
                yield f"[API CONNECTION ERROR: {str(e)}]"
                return

        # 3. Local LLaMA GGUF Streaming (Default)
        else:
            if not await asyncio.to_thread(self.ensure_loaded):
                yield "[SYSTEM NOTICE: AI Model is not loaded or missing. Please verify model weights in the models directory.]"
                return

            if self.is_busy:
                logger.info("Local inference engine busy. Queuing request.")

            async with self.lock:
                loop = asyncio.get_running_loop()
                token_queue = asyncio.Queue(maxsize=128)
                stop_event = threading.Event()

                def _producer():
                    try:
                        stream = self.llm.create_chat_completion(
                            messages=messages,
                            stream=True,
                            temperature=0.2,
                            max_tokens=MAX_OUTPUT_TOKENS,
                            stop=["<|eot_id|>", "<|end_of_text|>"]
                        )
                        for chunk in stream:
                            if stop_event.is_set():
                                break
                            choices = chunk.get('choices', [])
                            if choices:
                                delta = choices[0].get('delta', {})
                                content = delta.get('content')
                                if content:
                                    loop.call_soon_threadsafe(token_queue.put_nowait, content)
                    except Exception as ex:
                        logger.error(f"Inference Thread Error: {ex}", exc_info=True)
                        loop.call_soon_threadsafe(token_queue.put_nowait, ex)
                    finally:
                        loop.call_soon_threadsafe(token_queue.put_nowait, None)

                # Dedicated inference worker thread (eliminates per-token threadpool switching)
                worker = threading.Thread(target=_producer, daemon=True)
                worker.start()

                try:
                    while True:
                        token = await token_queue.get()
                        if token is None:
                            break
                        if isinstance(token, Exception):
                            yield f"[INFERENCE ERROR: {str(token)}]"
                            break
                        yield token
                finally:
                    # Clean cancellation: stops C++ generation immediately if consumer aborts or disconnects
                    stop_event.set()


# Singleton instance
tars_engine = TarsEngine()