import os
import sys
import time
from pathlib import Path
import requests

# Fix Windows console UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL_URL = "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
FILENAME = "qwen2.5-3b-instruct-q4_k_m.gguf"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
TARGET_FILE = MODELS_DIR / FILENAME
EXPECTED_SIZE = 2104932768  # 2.10 GB (1.96 GiB)

def download_model():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Downloading {FILENAME} via huggingface_hub...")
    print(f"[INFO] Destination: {TARGET_FILE}")
    try:
        from huggingface_hub import hf_hub_download
        path = hf_hub_download(
            repo_id="Qwen/Qwen2.5-3B-Instruct-GGUF",
            filename=FILENAME,
            local_dir=str(MODELS_DIR),
        )
        print(f"\n[SUCCESS] Successfully downloaded to {path}!")
        return True
    except Exception as e:
        print(f"\n[ERROR] Download failed: {e}")
        return False

if __name__ == "__main__":
    success = download_model()
    sys.exit(0 if success else 1)
