import os
import sys
from pathlib import Path
from core.utils.text_extractor import extract_text_from_file

# --- CONFIGURATION ---
pdf_path = "Lec03_RAGFundamentals2.pdf" 
pptx_path = "Information-security-G2.pptx"

def test_imports():
    print("--- 1. Testing Core Document Libraries ---")
    try:
        import pypdf
        print("[OK] pypdf found.")
    except ImportError:
        print("[ERROR] pypdf missing. Run: pip install pypdf")
        return False

    try:
        import pptx 
        print("[OK] python-pptx found.")
    except ImportError:
        print("[ERROR] python-pptx missing. Run: pip install python-pptx")
        return False

    try:
        import docx
        print("[OK] python-docx found.")
    except ImportError:
        print("[ERROR] python-docx missing. Run: pip install python-docx")
        return False
        
    return True

def test_unified_extractor():
    print("\n--- 2. Testing Unified Native Text Extractor ---")
    
    # Test on any existing files in data/books or current dir
    test_files = [pdf_path, pptx_path]
    books_dir = Path("data/books")
    if books_dir.exists():
        for b in books_dir.iterdir():
            if b.is_dir():
                for f in b.iterdir():
                    if f.suffix.lower() in ('.pdf', '.epub', '.pptx', '.docx'):
                        test_files.append(str(f))
                        break
            if len(test_files) >= 5:
                break

    for fpath in test_files:
        p = Path(fpath)
        if not p.exists():
            continue
        try:
            print(f"   > Extracting '{p.name}' ({p.suffix})...")
            text = extract_text_from_file(str(p))
            preview = text[:80].replace('\n', ' ') if text else "None"
            print(f"     [SUCCESS] Extracted {len(text)} characters. Sample: {preview}...")
        except Exception as ex:
            print(f"     [FAILED] Extraction error: {ex}")

if __name__ == "__main__":
    print("STARTING DIAGNOSTIC (Libre-Library Native Pipeline)...")
    if test_imports():
        test_unified_extractor()
    print("\nDIAGNOSTIC COMPLETE.")