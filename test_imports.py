# test_imports.py
import sys
print(f"Python version: {sys.version}")

try:
    import docx
    print(f"✅ python-docx imported. Module location: {docx.__file__}")
except ImportError as e:
    print(f"❌ Failed to import python-docx: {e}")

try:
    from pptx import Presentation
    print(f"✅ python-pptx imported. Module location: {Presentation.__module__}")
except ImportError as e:
    print(f"❌ Failed to import python-pptx: {e}")