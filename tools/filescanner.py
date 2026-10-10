import os
from pathlib import Path
from typing import Optional, Set

BASE_DIR = Path(__file__).resolve().parent.parent

# Files and folders to completely ignore
IGNORE_DIRS: Set[str] = {'.venv', '__pycache__', '.git', '.idea', '.vscode'}
ALLOWED_EXTENSIONS: Set[str] = {'.py'}


def scan_project(output_path: Optional[Path] = None) -> Path:
    """
    Scans project python source files and aggregates them into a summary file.
    Fast, memory-efficient, and cleanly modularized.
    """
    target = output_path or (BASE_DIR / "project_summary.txt")
    with open(target, "w", encoding="utf-8") as outfile:
        for root, dirs, files in os.walk(BASE_DIR):
            # Modify dirs in-place to skip ignored directories
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

            for file in sorted(files):
                ext = os.path.splitext(file)[1]
                if ext in ALLOWED_EXTENSIONS:
                    filepath = os.path.join(root, file)

                    # Do not scan self
                    if file == "filescanner.py":
                        continue

                    outfile.write(f"\n{'='*60}\n")
                    outfile.write(f"FILE: {filepath}\n")
                    outfile.write(f"{'='*60}\n")

                    try:
                        with open(filepath, "r", encoding="utf-8") as infile:
                            outfile.write(infile.read() + "\n")
                    except Exception as e:
                        outfile.write(f"[Error reading file: {e}]\n")

    return target


if __name__ == "__main__":
    out = scan_project()
    print(f"Done! Open {out}, copy the contents, and paste them to your AI assistant.")
