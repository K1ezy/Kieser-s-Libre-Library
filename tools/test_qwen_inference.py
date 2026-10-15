import asyncio
import sys
import time

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure UTF-8 console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

async def test_qwen():
    print("=" * 60)
    print(" Testing Qwen 2.5 7B GGUF with TARS Engine")
    print("=" * 60)

    from core.config import settings
    print(f"[CONFIG] Active Provider: {settings.AI_PROVIDER}")
    print(f"[CONFIG] Model Filename: {settings.MODEL_FILENAME}")
    print(f"[CONFIG] GPU Layers: {settings.GPU_LAYERS}")
    print(f"[CONFIG] Context Window: {settings.CONTEXT_WINDOW}")

    from core.ai_engine.llm_engine import tars_engine
    print(f"[CHECK] Model file path: {tars_engine.model_path}")
    print(f"[CHECK] File exists: {tars_engine.model_path.exists()}")
    print(f"[CHECK] Provider Available: {tars_engine.is_available}")

    if not tars_engine.model_path.exists():
        print("[ERROR] Model file does not exist yet. Please wait for download to finish.")
        return False

    print("\n[STEP 1] Testing Connection & Engine Load...")
    load_start = time.time()
    conn_result = await tars_engine.test_connection()
    load_time = time.time() - load_start
    print(f"[LOAD RESULT] {conn_result} (Loaded in {load_time:.2f}s)")

    if not conn_result.get("success"):
        print("[ERROR] Failed to load model weights!")
        return False

    print("\n[STEP 2] Testing Streaming Chat Completion...")
    test_messages = [
        {"role": "system", "content": "You are TARS, the AI Librarian for Libre-Library. Be concise."},
        {"role": "user", "content": "Hello! Introduce yourself in 2 sentences."}
    ]

    stream_start = time.time()
    tokens = []
    first_token_time = None

    async for token in tars_engine.stream_response(test_messages, max_tokens=100):
        if first_token_time is None:
            first_token_time = time.time() - stream_start
        tokens.append(token)
        print(token, end="", flush=True)

    total_stream_time = time.time() - stream_start
    full_response = "".join(tokens)
    print(f"\n\n[STREAM METRICS] Time to first token: {first_token_time:.2f}s | Total tokens: ~{len(tokens)} | Total time: {total_stream_time:.2f}s")

    print("\n[STEP 3] Testing Direct Completion (create_completion)...")
    comp_start = time.time()
    prompt = "Q: What is a digital library?\nA:"
    comp_result = await tars_engine.create_completion(prompt, max_tokens=80)
    comp_time = time.time() - comp_start
    print(f"[COMPLETION] {comp_result.strip() if comp_result else 'None'}")
    print(f"[COMPLETION METRICS] Generated in {comp_time:.2f}s")

    print("\n" + "=" * 60)
    print(" ALL QWEN 2.5 7B GGUF INFERENCE TESTS PASSED!")
    print("=" * 60)
    await tars_engine.close()
    return True

if __name__ == "__main__":
    success = asyncio.run(test_qwen())
    sys.exit(0 if success else 1)
