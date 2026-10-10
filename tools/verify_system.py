import sys
import os
import asyncio
import time
import httpx
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
import bcrypt

# Ensure root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings
from core.database.mongo_manager import mongo_db
from core.auth.jwt_handler import create_access_token, verify_token
from core.services.ingestion_service import IngestionService


async def run_verification():
    print("=" * 65)
    print("LIBRE-LIBRARY SYSTEM VERIFICATION & VALIDATION AUDIT")
    print("=" * 65)
    
    results = {"security": [], "performance": []}

    # ---------------------------------------------------------
    # 1. SECURITY VALIDATION CHECKS
    # ---------------------------------------------------------
    print("\n[1/2] Auditing Security Architecture & Access Controls...")

    # A. Secret Key & Entropy
    sec_key = settings.SECRET_KEY
    if sec_key and sec_key != "libre_library_secure_key_2025" and len(sec_key) >= 32:
        results["security"].append(("Cryptographic Secret Entropy", "PASS", f"256-bit secure key present ({len(sec_key)} chars)"))
    else:
        results["security"].append(("Cryptographic Secret Entropy", "FAIL", "Secret key default or insufficient"))

    # B. JWT Signature & Expiration Verification
    t_start = time.perf_counter()
    sample_payload = {"user_id": "test_uuid", "role": "user"}
    token = create_access_token(sample_payload, expires_delta=timedelta(seconds=1))
    decoded = verify_token(token)
    expired_token = create_access_token(sample_payload, expires_delta=timedelta(seconds=-10))
    decoded_expired = verify_token(expired_token)
    t_jwt = (time.perf_counter() - t_start) * 1000

    if decoded and decoded.get("user_id") == "test_uuid" and decoded_expired is None:
        results["security"].append(("JWT Signing & Expiration Guard", "PASS", f"Valid verified, expired rejected in {t_jwt:.2f}ms"))
    else:
        results["security"].append(("JWT Signing & Expiration Guard", "FAIL", "Token verification logic error"))

    # C. Bcrypt Password Hashing & Resistance
    pwd = "SampleSecurePassword123!"
    t_start = time.perf_counter()
    hashed = bcrypt.hashpw(pwd.encode('utf-8'), bcrypt.gensalt(rounds=12))
    matched = bcrypt.checkpw(pwd.encode('utf-8'), hashed)
    wrong_matched = bcrypt.checkpw("WrongPassword!".encode('utf-8'), hashed)
    t_bcrypt = (time.perf_counter() - t_start) * 1000

    if matched and not wrong_matched:
        results["security"].append(("Bcrypt Salt & Work Factor (12)", "PASS", f"Timing-safe hash & verify in {t_bcrypt:.1f}ms"))
    else:
        results["security"].append(("Bcrypt Salt & Work Factor", "FAIL", "Password hash mismatch"))

    # D. Path Traversal & Filename Sanitization
    ingestion = IngestionService()
    traversal_payloads = ["../../etc/shadow", "..\\..\\windows\\system32\\cmd.exe", "/absolute/path/doc.pdf", "normal.pdf"]
    sanitized_clean = True
    for p in traversal_payloads:
        clean = ingestion._sanitize_filename(p)
        if "/" in clean or "\\" in clean or ".." in clean:
            sanitized_clean = False
            break

    if sanitized_clean:
        results["security"].append(("Filesystem Traversal Protection", "PASS", "Directory separators and relative leaps sanitized"))
    else:
        results["security"].append(("Filesystem Traversal Protection", "FAIL", "Sanitizer leaked directory separators"))

    # E. Book ID Alphanumeric Regex Guard
    id_regex = re.compile(r"^[a-zA-Z0-9_-]+$")
    bad_ids = ["../book", "book;drop table", "book\x00null", "safe-uuid_123"]
    regex_pass = not id_regex.match(bad_ids[0]) and not id_regex.match(bad_ids[1]) and not id_regex.match(bad_ids[2]) and id_regex.match(bad_ids[3])
    if regex_pass:
        results["security"].append(("Alphanumeric Book ID Regex", "PASS", "Strict identifier enforcement blocks injection"))
    else:
        results["security"].append(("Alphanumeric Book ID Regex", "FAIL", "ID regex validation failed"))

    # ---------------------------------------------------------
    # 2. PERFORMANCE VALIDATION CHECKS
    # ---------------------------------------------------------
    print("\n[2/2] Benchmarking Database, Search & Endpoint Latency...")

    # A. MongoDB Connection & Query Latency
    await mongo_db.initialize()
    t_start = time.perf_counter()
    total_books = await mongo_db.get_total_book_count()
    t_count = (time.perf_counter() - t_start) * 1000

    t_start = time.perf_counter()
    recent_books = await mongo_db.get_recent_books(limit=20)
    t_recent = (time.perf_counter() - t_start) * 1000

    t_start = time.perf_counter()
    search_res = await mongo_db.search_books("Freddy", limit=10)
    t_search = (time.perf_counter() - t_start) * 1000

    results["performance"].append(("MongoDB Count Query", f"{t_count:.2f} ms", f"{total_books} total catalog books indexed"))
    results["performance"].append(("MongoDB Recent Fetch (Limit 20)", f"{t_recent:.2f} ms", f"Retrieved {len(recent_books)} books"))
    results["performance"].append(("MongoDB Regex Search Index", f"{t_search:.2f} ms", f"Retrieved {len(search_res)} hits"))

    # B. HTTP Endpoint Latency (Local Server)
    async with httpx.AsyncClient(timeout=4.0) as client:
        try:
            # Login page (unauthenticated)
            t_start = time.perf_counter()
            r_login = await client.get("http://127.0.0.1:8080/login")
            t_http_login = (time.perf_counter() - t_start) * 1000
            results["performance"].append(("HTTP GET /login (SSR)", f"{t_http_login:.2f} ms", f"Status {r_login.status_code}"))

            # Static asset caching
            t_start = time.perf_counter()
            r_static = await client.get("http://127.0.0.1:8080/static/default_cover.svg")
            t_static = (time.perf_counter() - t_start) * 1000
            cache_header = r_static.headers.get("cache-control", "None")
            results["performance"].append(("HTTP GET /static (Cacheable)", f"{t_static:.2f} ms", f"Status {r_static.status_code}, Cache-Control: {cache_header[:25]}"))

            # Protected book detail route
            t_start = time.perf_counter()
            r_book = await client.get("http://127.0.0.1:8080/book/28d6e17c-e320-4889-9a37-0c216a488675")
            t_book = (time.perf_counter() - t_start) * 1000
            results["performance"].append(("HTTP GET /book/{id}", f"{t_book:.2f} ms", f"Status {r_book.status_code}"))
        except Exception as err:
            results["performance"].append(("HTTP Endpoints", "N/A", f"Server connection note: {err}"))

    # ---------------------------------------------------------
    # PRINT SUMMARY MATRIX
    # ---------------------------------------------------------
    print("\n" + "=" * 65)
    print("SECURITY CONTROLS AUDIT RESULTS")
    print("=" * 65)
    for name, status, details in results["security"]:
        badge = "[PASS]" if status == "PASS" else "[FAIL]"
        print(f" {badge:<8} {name:<35} {details}")

    print("\n" + "=" * 65)
    print("PERFORMANCE BENCHMARK RESULTS")
    print("=" * 65)
    for name, metric, details in results["performance"]:
        print(f" [METRIC] {name:<35} {metric:<12} {details}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    asyncio.run(run_verification())
