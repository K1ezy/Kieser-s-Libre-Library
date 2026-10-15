import sys
from pathlib import Path
from sentence_transformers import SentenceTransformer

# Fix Windows console UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Configuration
BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_SAVE_PATH = MODELS_DIR / EMBEDDING_MODEL_NAME

LLM_REPO_ID = "Qwen/Qwen2.5-3B-Instruct-GGUF"
LLM_FILENAME = "qwen2.5-3b-instruct-q4_k_m.gguf"
LLM_SAVE_PATH = MODELS_DIR / LLM_FILENAME

def download_embedding_model():
    print(f"\n[INFO] Checking embedding model: {EMBEDDING_MODEL_NAME}")
    print(f"[INFO] Destination: {EMBEDDING_SAVE_PATH}")
    EMBEDDING_SAVE_PATH.mkdir(parents=True, exist_ok=True)

    try:
        model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        model.save(str(EMBEDDING_SAVE_PATH))
        print(f"[SUCCESS] Embedding model ready at: {EMBEDDING_SAVE_PATH}")
        return True
    except Exception as e:
        print(f"[ERROR] Embedding model download failed: {e}")
        return False

def download_llm_model():
    print(f"\n[INFO] Checking local LLM weights: {LLM_FILENAME}")
    print(f"[INFO] Source Repo: {LLM_REPO_ID}")
    print(f"[INFO] Destination: {LLM_SAVE_PATH}")

    from tools.download_qwen import download_model as dl_qwen
    return dl_qwen()

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--llm" in args:
        download_llm_model()
    elif "--all" in args:
        print("=" * 60)
        print(" Libre-Library Offline Model Setup (all-MiniLM + Qwen2.5-7B)")
        print("=" * 60)
        download_embedding_model()
        download_llm_model()
    elif "--embedding" in args:
        download_embedding_model()
    else:
        # Default behavior: download embedding model (compatible with Docker build)
        download_embedding_model()
        if LLM_SAVE_PATH.exists():
            print(f"[OK] LLM weights present: {LLM_FILENAME} ({LLM_SAVE_PATH.stat().st_size:,} bytes)")
        else:
            print(f"[INFO] To download offline LLM weights ({LLM_FILENAME}), run: python download_model.py --llm")