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
FUNCTIONAL_CONTEXT_LIMIT = 4096
DEFAULT_CHAT_MAX_TOKENS = 1500
MAX_OUTPUT_TOKENS = 2048
MAX_RAG_CHARS = 10000
MAX_LOCAL_QUEUE_DEPTH = 4
LOCAL_QUEUE_TIMEOUT = 45.0


class TarsEngine:
    """
    Multi-Provider AI Engine for Libre-Library:
    1. Local GGUF (llama-cpp-python) with lazy loading, bounded queue & GPU offloading
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

        # Local Llama-cpp state & bounded concurrency controls
        self.llm = None
        self._load_lock = threading.Lock()
        self.lock = asyncio.Lock()
        self._queue_semaphore = asyncio.Semaphore(MAX_LOCAL_QUEUE_DEPTH)
        self._waiting_requests = 0
        self.context_window = min(settings.CONTEXT_WINDOW, 4096)
        self.model_path = settings.MODEL_DIR / settings.MODEL_FILENAME
        self._is_loaded = False
        self._db_loaded = False
        self._http_client: Optional[httpx.AsyncClient] = None

        logger.info(f"TARS Engine initialized (Active Provider: {self.provider.upper()}, CTX: {self.context_window})")

    def _get_http_client(self, timeout: float = 60.0) -> httpx.AsyncClient:
        """Returns or creates a persistent connection-pooled HTTP client for sub-50ms latency."""
        if self._http_client is None or self._http_client.is_closed:
            limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
            self._http_client = httpx.AsyncClient(timeout=timeout, limits=limits)
        return self._http_client

    async def close(self):
        """Closes persistent HTTP client connection pool and releases resources."""
        if self._http_client and not self._http_client.is_closed:
            try:
                await self._http_client.aclose()
            except Exception as e:
                logger.debug(f"Error closing LLMEngine HTTP client: {e}")
            finally:
                self._http_client = None

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
        if "ollama_url" in config:
            self.ollama_url = config["ollama_url"].rstrip('/')
        if "ollama_model" in config:
            self.ollama_model = config["ollama_model"]
        if "openai_url" in config:
            self.openai_url = config["openai_url"].rstrip('/')
        if "openai_key" in config:
            self.openai_key = config["openai_key"]
        if "openai_model" in config:
            self.openai_model = config["openai_model"]
        logger.info(f"TARS Engine dynamically switched to: {self.provider.upper()}")

    @property
    def is_available(self) -> bool:
        """Returns True if the active provider is configured and ready."""
        if self.provider == 'local':
            return self.model_path.exists()
        elif self.provider == 'ollama':
            return bool(self.ollama_url and self.ollama_model)
        elif self.provider == 'openai':
            return bool(
                self.openai_url and (self.openai_key or "localhost" in self.openai_url or "127.0.0.1" in self.openai_url)
            )
        return False

    @property
    def is_busy(self) -> bool:
        """Returns True if the local model is currently executing inference."""
        return self.lock.locked()

    @property
    def queue_depth(self) -> int:
        """Returns the number of requests currently waiting for local inference."""
        return self._waiting_requests

    def _has_openai_fallback(self) -> bool:
        return bool(self.openai_url and self.openai_key)

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
                import os
                logger.info(
                    f"Loading Local TARS Engine: {settings.MODEL_FILENAME} "
                    f"(CTX: {self.context_window}, GPU: {settings.GPU_LAYERS})"
                )
                gpu_layers = settings.GPU_LAYERS
                cpu_ct = os.cpu_count() or 6
                threads = min(8, max(4, cpu_ct - 2 if cpu_ct > 6 else cpu_ct))

                try:
                    self.llm = Llama(
                        model_path=str(self.model_path),
                        n_ctx=self.context_window,
                        n_gpu_layers=gpu_layers,
                        n_threads=threads,
                        n_threads_batch=threads,
                        flash_attn=True,
                        use_mmap=True,
                        use_mlock=False,
                        verbose=False,
                        n_batch=512,
                        chat_format="llama-3"
                    )
                except Exception as fa_err:
                    logger.debug(f"Flash attention init notice ({fa_err}). Falling back to standard attention.")
                    self.llm = Llama(
                        model_path=str(self.model_path),
                        n_ctx=self.context_window,
                        n_gpu_layers=gpu_layers,
                        n_threads=threads,
                        n_threads_batch=threads,
                        use_mmap=True,
                        use_mlock=False,
                        verbose=False,
                        n_batch=512,
                        chat_format="llama-3"
                    )

                self._is_loaded = True
                logger.info(f"Local TARS Engine Initialization: COMPLETE (Threads: {threads}, CTX: {self.context_window})")
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
                return {"success": False, "provider": "local", "message": f"GGUF model not found at {self.model_path}"}
            ready = await asyncio.to_thread(self.ensure_loaded)
            return {
                "success": ready,
                "provider": "local",
                "model": settings.MODEL_FILENAME,
                "queue_depth": self._waiting_requests,
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
                        msg = (
                            f"Ollama online. Model '{self.ollama_model}' detected."
                            if has_model else
                            f"Ollama online, but model '{self.ollama_model}' not installed."
                        )
                        return {"success": True, "provider": "ollama", "model": self.ollama_model, "message": msg}
                    return {"success": False, "provider": "ollama", "message": f"Ollama returned HTTP status {resp.status_code}."}
            except Exception as e:
                return {"success": False, "provider": "ollama", "message": f"Cannot connect to Ollama at {self.ollama_url}: {e}"}

        elif self.provider == 'openai':
            try:
                headers = {"Authorization": f"Bearer {self.openai_key}"} if self.openai_key else {}
                async with httpx.AsyncClient(timeout=6.0) as client:
                    url = f"{self.openai_url}/models"
                    resp = await client.get(url, headers=headers)
                    if resp.status_code in (200, 404):
                        return {"success": True, "provider": "openai", "model": self.openai_model, "message": f"OpenAI endpoint online ({url})."}
                    return {"success": False, "provider": "openai", "message": f"Endpoint returned HTTP status {resp.status_code}."}
            except Exception as e:
                return {"success": False, "provider": "openai", "message": f"Cannot connect to API endpoint: {e}"}

        return {"success": False, "provider": self.provider, "message": f"Unknown provider '{self.provider}'"}

    async def _complete_via_openai(
        self, prompt: str, max_tokens: int, temperature: float, stop: Optional[List[str]]
    ) -> Optional[str]:
        try:
            headers = {"Authorization": f"Bearer {self.openai_key}"} if self.openai_key else {}
            headers["Content-Type"] = "application/json"
            client = self._get_http_client(timeout=60.0)
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

    async def create_completion(
        self,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        stop: Optional[List[str]] = None
    ) -> Optional[str]:
        """Thread-safe and async-safe completion across all 3 providers with bounded local queue."""
        await self.ensure_db_settings_loaded()

        # 1. Ollama Provider
        if self.provider == 'ollama':
            try:
                client = self._get_http_client(timeout=60.0)
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
            return await self._complete_via_openai(prompt, max_tokens, temperature, stop)

        # 3. Local LLaMA GGUF Provider (Default) with Bounded Queue & Timeout
        else:
            if not await asyncio.to_thread(self.ensure_loaded):
                logger.error("create_completion: Local model could not be loaded.")
                return None

            if self._waiting_requests >= MAX_LOCAL_QUEUE_DEPTH:
                if self._has_openai_fallback():
                    logger.warning("Local inference queue full; failing over to OpenAI-compatible endpoint.")
                    return await self._complete_via_openai(prompt, max_tokens, temperature, stop)
                logger.warning("Local inference queue saturated; rejecting request early.")
                return None

            self._waiting_requests += 1
            try:
                async with self._queue_semaphore:
                    await asyncio.wait_for(self.lock.acquire(), timeout=LOCAL_QUEUE_TIMEOUT)
                    try:
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
                    finally:
                        self.lock.release()
            except asyncio.TimeoutError:
                logger.warning("Timed out waiting for local LLM lock in create_completion.")
                if self._has_openai_fallback():
                    return await self._complete_via_openai(prompt, max_tokens, temperature, stop)
                return None
            finally:
                self._waiting_requests = max(0, self._waiting_requests - 1)

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

    async def _stream_via_openai(self, messages: list, effective_max_tokens: int) -> AsyncGenerator[str, None]:
        try:
            headers = {"Authorization": f"Bearer {self.openai_key}"} if self.openai_key else {}
            headers["Content-Type"] = "application/json"
            client = self._get_http_client(timeout=120.0)
            payload = {
                "model": self.openai_model,
                "messages": messages,
                "stream": True,
                "temperature": 0.2,
                "max_tokens": effective_max_tokens
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
        except Exception as e:
            logger.error(f"OpenAI streaming failure: {e}")
            yield f"[API CONNECTION ERROR: {str(e)}]"

    async def stream_response(self, messages: list, max_tokens: Optional[int] = None) -> AsyncGenerator[str, None]:
        """Streams chat tokens asynchronously across Local, Ollama, and OpenAI providers with bounded queuing."""
        await self.ensure_db_settings_loaded()
        effective_max_tokens = max_tokens or DEFAULT_CHAT_MAX_TOKENS

        # Clean / truncate context if overly huge
        if messages and isinstance(messages[0], dict) and "content" in messages[0]:
            system_message = messages[0]['content']
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
                client = self._get_http_client(timeout=120.0)
                payload = {
                    "model": self.ollama_model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": 0.2,
                        "num_predict": effective_max_tokens
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
            async for chunk in self._stream_via_openai(messages, effective_max_tokens):
                yield chunk
            return

        # 3. Local LLaMA GGUF Streaming (Default)
        else:
            if not await asyncio.to_thread(self.ensure_loaded):
                yield "[SYSTEM NOTICE: AI Model is not loaded or missing. Please verify model weights in the models directory.]"
                return

            if self._waiting_requests >= MAX_LOCAL_QUEUE_DEPTH:
                if self._has_openai_fallback():
                    logger.warning("Local inference queue saturated; streaming via fallback OpenAI endpoint.")
                    async for chunk in self._stream_via_openai(messages, effective_max_tokens):
                        yield chunk
                    return
                yield "[SYSTEM NOTICE: TARS local AI engine is currently serving maximum concurrent readers. Please try again in a few seconds.]"
                return

            if self.is_busy:
                logger.info(f"Local inference engine busy (queue depth: {self._waiting_requests + 1}). Queuing request.")

            self._waiting_requests += 1
            lock_acquired = False
            try:
                await asyncio.wait_for(self.lock.acquire(), timeout=LOCAL_QUEUE_TIMEOUT)
                lock_acquired = True

                loop = asyncio.get_running_loop()
                token_queue: asyncio.Queue = asyncio.Queue(maxsize=0)
                stop_event = threading.Event()

                def _producer():
                    try:
                        stream = self.llm.create_chat_completion(
                            messages=messages,
                            stream=True,
                            temperature=0.2,
                            max_tokens=effective_max_tokens,
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
                except asyncio.CancelledError:
                    logger.info("Client disconnected mid-stream; signaling local GGUF thread to abort.")
                    stop_event.set()
                    raise
                finally:
                    stop_event.set()
            except asyncio.TimeoutError:
                if self._has_openai_fallback():
                    logger.warning("Local queue wait timed out; failing over to OpenAI stream.")
                    async for chunk in self._stream_via_openai(messages, effective_max_tokens):
                        yield chunk
                else:
                    yield "[SYSTEM NOTICE: Local AI queue timed out under heavy load. Please retry shortly.]"
            finally:
                if lock_acquired:
                    self.lock.release()
                self._waiting_requests = max(0, self._waiting_requests - 1)


# Singleton instance
tars_engine = TarsEngine()