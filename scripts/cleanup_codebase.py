import ast
import os
import shutil
from pathlib import Path
from typing import Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent
Protected_Entrypoints = {
    "main.py",
    "app.py",
    "app_startup.py",
    "conftest.py",
    "cleanup_codebase.py",
    "smart_librarian.py",
}
IGNORE_DIRS = {".git", ".venv", "venv", "env", "node_modules", "data", "models", ".idea", ".nicegui", ".ruff_cache"}


def purge_cache_and_temp_artifacts(root: Path) -> int:
    """Removes __pycache__ directories and .pyc / .pyo / .tmp / .bak files."""
    removed_count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        if "__pycache__" in dirnames:
            cache_dir = Path(dirpath) / "__pycache__"
            shutil.rmtree(cache_dir, ignore_errors=True)
            dirnames.remove("__pycache__")
            removed_count += 1

        for fname in filenames:
            if fname.endswith((".pyc", ".pyo", ".tmp", ".bak", ".orig")):
                try:
                    (Path(dirpath) / fname).unlink()
                    removed_count += 1
                except OSError:
                    pass
    return removed_count


def find_unreferenced_python_files(root: Path) -> Set[Path]:
    """
    Statically analyzes all AST imports across the project to report orphaned .py files.
    """
    all_py_files: Set[Path] = set()
    imported_stems: Set[str] = set()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fname in filenames:
            if fname.endswith(".py"):
                full_path = Path(dirpath) / fname
                all_py_files.add(full_path)

                try:
                    source = full_path.read_text(encoding="utf-8", errors="ignore")
                    tree = ast.parse(source)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                for part in alias.name.split("."):
                                    imported_stems.add(part)
                        elif isinstance(node, ast.ImportFrom) and node.module:
                            for part in node.module.split("."):
                                imported_stems.add(part)
                            for alias in node.names:
                                imported_stems.add(alias.name)
                except Exception:
                    pass

    orphans: Set[Path] = set()
    for py_path in all_py_files:
        if py_path.name in Protected_Entrypoints or py_path.name.startswith("test_"):
            continue
        if py_path.parent.name in ("pages", "tests", "migrations", "components"):
            continue
        if py_path.stem not in imported_stems and py_path.name != "__init__.py":
            orphans.add(py_path.relative_to(root))

    return orphans


if __name__ == "__main__":
    cleaned = purge_cache_and_temp_artifacts(PROJECT_ROOT)
    print(f"[Cleanup] Removed {cleaned} cache/temp directories and artifacts.")

    orphans = find_unreferenced_python_files(PROJECT_ROOT)
    if orphans:
        print("\n[Audit] Potentially unreferenced Python files detected:")
        for p in sorted(orphans):
            print(f"  - {p}")
    else:
        print("\n[Audit] Zero orphaned Python modules found.")
