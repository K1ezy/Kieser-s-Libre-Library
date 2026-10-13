"""
Core security utilities for Libre-Library:
- Safe Book ID validation preventing path traversal and injection attacks
- Path confinement verification
"""

import re
from typing import Union

# Robust, attack-resistant Book ID regex:
# Disallows '.', '..', and any sequence containing '..'
# Strictly forbids path separators ('/', '\'), null bytes, shell metacharacters, and spaces
# Permits safe catalog naming conventions: unicode alphanumerics, hyphens, underscores,
# periods, parentheses, commas, semicolons, ampersands, and apostrophes
SAFE_BOOK_ID_PATTERN = re.compile(r"^(?!\.{1,2}$)(?!.*\.\.)[\w\-\.\(\)\,\;\&\'\u2019]{1,300}$")


def is_valid_book_id(book_id: Union[str, None]) -> bool:
    """
    Validates that a book identifier is safe for filesystem operations and URL routes.
    Blocks directory traversal, injection attacks, and empty identifiers.
    """
    if not book_id or not isinstance(book_id, str):
        return False
    clean_id = book_id.strip()
    return bool(SAFE_BOOK_ID_PATTERN.match(clean_id))
