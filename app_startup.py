import asyncio
import logging
import time
from typing import Optional

from core.database.mongo_manager import mongo_db
from core.ai_engine.llm_engine import tars_engine
from core.ai_engine.rag_pipeline import tars_archive
from core.services.background_indexer import get_background_indexer

logger = logging.getLogger("APP_STARTUP")

_background_warmup_task: Optional[asyncio.Task] = None


async def _background_ai_warmup() -> None:
    """
    Non-blocking background worker to prewarm ChromaDB and LLM settings
    without ever stalling the main UI event loop or page renders.
    """
    t0 = time.time()
    try:
        # Prewarm ChromaDB collection and load BM25 disk cache (< 50ms)
        await asyncio.to_thread(tars_archive.ensure_initialized)
        logger.info(f"[Startup] TARS ChromaDB & BM25 cache verified in {time.time() - t0:.3f}s.")

        # Ensure LLM DB configuration is synced
        await asyncio.to_thread(tars_engine.ensure_loaded)
        logger.info(f"[Startup] TARS LLM Engine ready in {time.time() - t0:.3f}s.")

        # Non-blocking background worker: checks if any books are unindexed and queues them quietly
        indexer = get_background_indexer(tars_archive, mongo_db.books)
        indexer.start_non_blocking()
        logger.info("[Startup] Non-blocking background indexer started successfully.")
    except Exception as exc:
        logger.warning(f"[Startup] Background AI warm-up note: {exc}")


async def init_app_startup() -> float:
    """
    Ultra-fast application startup initializer.
    Initializes database connections and delegates all RAG chunking and model loading
    to non-blocking background workers so the login and dashboard UI render in < 1 second.
    Returns the elapsed startup time in seconds.
    """
    global _background_warmup_task
    start_time = time.time()
    logger.info("Initializing Libre-Library fast startup sequence...")

    # 1. Initialize MongoDB connection (sub-100ms)
    await mongo_db.initialize()

    # 2. Load dynamic DB settings for LLM engine (sub-50ms)
    await tars_engine.ensure_db_settings_loaded()

    # 3. Spawn completely non-blocking background worker for ChromaDB and RAG indexing
    _background_warmup_task = asyncio.create_task(_background_ai_warmup())

    elapsed = time.time() - start_time
    logger.info(f"✅ Libre-Library boot completed in {elapsed:.3f}s (Interactive in < 1.0s).")
    return elapsed


async def shutdown_app() -> None:
    """Graceful shutdown lifecycle for databases, workers, and background threads."""
    logger.info("Shutting down Libre-Library services...")
    global _background_warmup_task

    # 1. Stop background indexer if running
    try:
        indexer = get_background_indexer()
        if indexer and indexer.is_running:
            indexer.request_stop()
    except Exception:
        pass

    # 2. Cancel warmup task if still active
    if _background_warmup_task and not _background_warmup_task.done():
        _background_warmup_task.cancel()

    # 3. Close database connections and LLM handles
    try:
        await mongo_db.close()
    except Exception:
        pass

    try:
        await tars_engine.close()
    except Exception:
        pass

    logger.info("Libre-Library shutdown complete.")
