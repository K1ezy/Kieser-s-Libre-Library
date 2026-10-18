import asyncio
import json
import logging
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional, Any
import httpx

from core.config import (
    AI_PROVIDER,
    BATCH_SIZE,
    CONTEXT_WINDOW,
    GPU_LAYERS,
    LLM_REPEAT_PENALTY,
    LLM_TEMPERATURE,
    LLM_TOP_P,
    MODEL_DIR,
    MODEL_FILENAME,
    OPENAI_API_BASE,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    PREFERRED_MODELS,
    settings,
)

logger = logging.getLogger(__name__)


class TarsEngine:
    """Singleton LLM engine supporting local GGUF (llama-cpp-python) and OpenAI endpoints."""

    def __init__(self):
        self.llm = None
        self.model_name = MODEL_FILENAME
        self.context_window = int(CONTEXT_WINDOW)
        self.temperature = LLM_TEMPERATURE
        self.top_p = LLM_TOP_P
        self.repeat_penalty = LLM_REPEAT_PENALTY
        self._stop_tokens = ["<|im_end|>", "<|eot_id|>", "</s>", "[/USER INQUIRY]"]
        self.provider = AI_PROVIDER.lower()
        self.openai_url = OPENAI_API_BASE.rstrip('/')
        self.openai_key = OPENAI_API_KEY
        self.openai_model = OPENAI_MODEL
        self._http_client: Optional[httpx.AsyncClient] = None
        self.lock = asyncio.Lock()
        self._db_loaded = False

    @property
    def model_path(self) -> Path:
        return self._resolve_model_path()

    @property
    def is_available(self) -> bool:
        if self.provider == 'local':
            return self._resolve_model_path().exists()
        return bool(self.openai_url)

    def _resolve_model_path(self) -> Path:
        primary = MODEL_DIR / self.model_name
        if primary.exists():
            return primary
        for fallback in PREFERRED_MODELS:
            candidate = MODEL_DIR / fallback
            if candidate.exists():
                logger.info("Primary model missing; falling back to %s", fallback)
                self.model_name = fallback
                return candidate
        return primary

    async def ensure_db_settings_loaded(self) -> None:
        """Loads persistent admin provider configurations from MongoDB on first use."""
        if getattr(self, "_db_loaded", False):
            return
        try:
            from core.database.mongo_manager import mongo_db
            if mongo_db.db is not None:
                sys_cfg = await mongo_db.get_system_settings()
                if sys_cfg:
                    self.provider = sys_cfg.get("ai_provider", self.provider).lower()
                    self.openai_url = sys_cfg.get("openai_url", self.openai_url).rstrip('/')
                    self.openai_key = sys_cfg.get("openai_key", self.openai_key)
                    self.openai_model = sys_cfg.get("openai_model", self.openai_model)
                    logger.info("TARS Engine re-configured from DB (Provider: %s).", self.provider.upper())
            self._db_loaded = True
        except Exception as e:
            logger.debug("DB settings load note: %s", e)

    def load_model(self) -> None:
        if self.llm is not None or self.provider != "local":
            return

        from llama_cpp import Llama

        model_path = self._resolve_model_path()
        if not model_path.exists():
            raise FileNotFoundError(f"GGUF model file not found at: {model_path}")

        import os
        cpu_ct = os.cpu_count() or 6
        gen_threads = min(8, max(4, cpu_ct - 2 if cpu_ct > 6 else cpu_ct))
        batch_threads = min(10, max(4, cpu_ct))

        try:
            self.llm = Llama(
                model_path=str(model_path),
                n_ctx=self.context_window,
                n_gpu_layers=GPU_LAYERS,
                n_batch=1024,
                n_ubatch=512,
                n_threads=gen_threads,
                n_threads_batch=batch_threads,
                flash_attn=True,
                verbose=False,
            )
        except Exception as fa_err:
            logger.debug("FlashAttention init notice (%s); falling back to standard attention.", fa_err)
            self.llm = Llama(
                model_path=str(model_path),
                n_ctx=self.context_window,
                n_gpu_layers=GPU_LAYERS,
                n_batch=1024,
                n_ubatch=512,
                n_threads=gen_threads,
                n_threads_batch=batch_threads,
                verbose=False,
            )
        logger.info(
            "Loaded GGUF model %s (n_ctx=%d, gpu_layers=%d, batch=1024, ubatch=512)",
            self.model_name,
            self.context_window,
            GPU_LAYERS,
        )

    def ensure_loaded(self) -> bool:
        try:
            self.load_model()
            return True
        except Exception as e:
            logger.error("Failed to load model: %s", e)
            return False

    def _get_http_client(self, timeout: float = 60.0) -> httpx.AsyncClient:
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
                logger.debug("Error closing LLMEngine HTTP client: %s", e)
            finally:
                self._http_client = None

    async def _stream_openai(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        top_p: float,
        max_tokens: int,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> AsyncGenerator[str, None]:
        try:
            headers = {"Authorization": f"Bearer {self.openai_key}"} if self.openai_key else {}
            headers["Content-Type"] = "application/json"
            client = self._get_http_client(timeout=120.0)
            payload = {
                "model": self.openai_model,
                "messages": messages,
                "stream": True,
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_tokens,
            }
            async with client.stream("POST", f"{self.openai_url}/chat/completions", json=payload, headers=headers) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    yield f"[API ERROR: Status {response.status_code} - {body.decode('utf-8', 'ignore')}]"
                    return
                async for line in response.aiter_lines():
                    if cancel_event and cancel_event.is_set():
                        break
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
            logger.error("OpenAI streaming failure: %s", e)
            yield f"[API CONNECTION ERROR: {str(e)}]"

    @property
    def is_busy(self) -> bool:
        return self.lock.locked()

    def configure(self, provider: str, config: Dict[str, Any]):
        self.provider = provider.lower()
        if "openai_url" in config:
            self.openai_url = config["openai_url"].rstrip('/')
        if "openai_key" in config:
            self.openai_key = config["openai_key"]
        if "openai_model" in config:
            self.openai_model = config["openai_model"]
        logger.info("TARS Engine dynamically switched to: %s", self.provider.upper())

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
                "model": self.model_name,
                "message": "Local GGUF model loaded and operational." if ready else "Failed to load GGUF model into memory."
            }
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

    async def stream_response(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        repeat_penalty: Optional[float] = None,
        max_tokens: int = 1024,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> AsyncGenerator[str, None]:
        """Streams tokens asynchronously with deterministic RAG sampling defaults."""
        await self.ensure_db_settings_loaded()
        if isinstance(temperature, int) and temperature > 2:
            max_tokens = temperature
            temperature = None

        eff_temp = self.temperature if temperature is None else temperature
        eff_top_p = self.top_p if top_p is None else top_p
        eff_repeat = self.repeat_penalty if repeat_penalty is None else repeat_penalty

        if self.provider == "openai":
            async for token in self._stream_openai(
                messages, eff_temp, eff_top_p, max_tokens, cancel_event
            ):
                yield token
            return

        self.load_model()
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

        def _producer():
            try:
                stream = self.llm.create_chat_completion(
                    messages=messages,
                    temperature=eff_temp,
                    top_p=eff_top_p,
                    repeat_penalty=eff_repeat,
                    max_tokens=max_tokens,
                    stop=self._stop_tokens,
                    stream=True,
                )
                for chunk in stream:
                    if cancel_event and cancel_event.is_set():
                        break
                    delta = (
                        chunk.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content")
                    )
                    if delta:
                        loop.call_soon_threadsafe(queue.put_nowait, delta)
            except Exception as exc:
                logger.error("Local GGUF inference error: %s", exc)
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    "\n\n*[Inference error: unable to complete generation.]*",
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        producer_future = loop.run_in_executor(None, _producer)
        try:
            while True:
                token = await queue.get()
                if token is None:
                    break
                yield token
        finally:
            if not producer_future.done():
                if cancel_event:
                    cancel_event.set()

    async def create_completion(
        self,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        stop: Optional[List[str]] = None,
    ) -> Optional[str]:
        if self.provider == "openai":
            try:
                headers = {"Authorization": f"Bearer {self.openai_key}"} if self.openai_key else {}
                client = self._get_http_client()
                resp = await client.post(
                    f"{self.openai_url}/chat/completions",
                    json={
                        "model": self.openai_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "stop": stop or self._stop_tokens,
                    },
                    headers=headers,
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"].strip()
                return None
            except Exception as ex:
                logger.error("OpenAI create_completion error: %s", ex)
                return None

        self.load_model()
        if not self.llm:
            return None

        def _infer():
            try:
                res = self.llm.create_completion(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stop=stop or self._stop_tokens,
                )
                return res["choices"][0]["text"]
            except Exception as ex:
                logger.error("Local GGUF create_completion error: %s", ex)
                return None

        return await asyncio.to_thread(_infer)

    async def generate_response(
        self,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        stop: Optional[List[str]] = None,
    ) -> Optional[str]:
        return await self.create_completion(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
        )


tars_engine = TarsEngine()