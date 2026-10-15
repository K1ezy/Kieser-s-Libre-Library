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
    
    if TARGET_FILE.exists():
        current_size = TARGET_FILE.stat().st_size
        if current_size == EXPECTED_SIZE:
            print(f"[OK] Model file already fully downloaded: {TARGET_FILE} ({current_size:,} bytes)")
            return True
        elif current_size > EXPECTED_SIZE:
            print(f"[WARN] Target file is larger than expected ({current_size:,} > {EXPECTED_SIZE:,}). Removing corrupted file.")
            TARGET_FILE.unlink()
            current_size = 0
        else:
            print(f"[RESUME] Resuming partial download from {current_size:,} bytes ({current_size / (1024**3):.2f} GB)...")
    else:
        current_size = 0

    headers = {}
    if current_size > 0:
        headers["Range"] = f"bytes={current_size}-"

    print(f"[INFO] Downloading: {FILENAME}")
    print(f"[INFO] Destination: {TARGET_FILE}")
    print(f"[INFO] Source: {MODEL_URL}")

    start_time = time.time()
    last_print = start_time
    bytes_downloaded = current_size

    try:
        response = requests.get(MODEL_URL, headers=headers, stream=True, timeout=30)
        
        if response.status_code == 416: # Range not satisfiable (already done)
            if TARGET_FILE.stat().st_size == EXPECTED_SIZE:
                print("[OK] Download already complete.")
                return True
        
        if response.status_code not in (200, 206):
            print(f"[ERROR] HTTP Error {response.status_code}: {response.text[:200]}")
            return False

        mode = "ab" if current_size > 0 and response.status_code == 206 else "wb"
        if mode == "wb":
            bytes_downloaded = 0

        total_size = EXPECTED_SIZE
        chunk_size = 1024 * 1024 * 4  # 4 MB chunks

        with open(TARGET_FILE, mode) as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                f.write(chunk)
                bytes_downloaded += len(chunk)
                
                now = time.time()
                if now - last_print >= 2.0:  # Log every 2 seconds
                    elapsed = now - start_time
                    speed = (bytes_downloaded - current_size) / (elapsed if elapsed > 0 else 1) / (1024 * 1024)
                    pct = (bytes_downloaded / total_size) * 100
                    gb_done = bytes_downloaded / (1024**3)
                    gb_total = total_size / (1024**3)
                    remaining_bytes = total_size - bytes_downloaded
                    eta_sec = remaining_bytes / (speed * 1024 * 1024) if speed > 0 else 0
                    print(f"[{pct:5.1f}%] {gb_done:.2f}/{gb_total:.2f} GB | Speed: {speed:5.1f} MB/s | ETA: {int(eta_sec // 60):02d}m {int(eta_sec % 60):02d}s")
                    sys.stdout.flush()
                    last_print = now

        final_size = TARGET_FILE.stat().st_size
        if final_size == EXPECTED_SIZE:
            print(f"\n[SUCCESS] {FILENAME} downloaded successfully ({final_size:,} bytes)!")
            return True
        else:
            print(f"\n[ERROR] Download finished but size mismatch: {final_size:,} vs {EXPECTED_SIZE:,}")
            return False

    except Exception as e:
        print(f"\n[ERROR] Download error: {e}")
        return False

if __name__ == "__main__":
    success = download_model()
    sys.exit(0 if success else 1)
