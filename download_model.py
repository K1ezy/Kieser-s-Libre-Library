import os
from pathlib import Path
from sentence_transformers import SentenceTransformer

# 1. Configuration
BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
MODEL_NAME = "all-MiniLM-L6-v2"
SAVE_PATH = MODELS_DIR / MODEL_NAME

def download_embedding_model():
    print(f"🚀 Starting download for: {MODEL_NAME}")
    print(f"📂 Destination: {SAVE_PATH}")

    # Create directory
    SAVE_PATH.mkdir(parents=True, exist_ok=True)

    try:
        # Download and save
        model = SentenceTransformer(MODEL_NAME)
        model.save(str(SAVE_PATH))
        print(f"\n✅ SUCCESS! Model saved to: {SAVE_PATH}")
        print("👉 You can now run the system fully offline.")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")

if __name__ == "__main__":
    download_embedding_model()