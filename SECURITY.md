# 🛡️ Security Policy

## Supported Versions

Libre-Library is actively maintained on the latest `main` branch.

| Version | Supported          |
| ------- | ------------------ |
| 1.x / `main` | :white_check_mark: |
| < 1.0   | :x:                |

---

## 🔒 Security Architecture Highlights

Libre-Library incorporates strict defense-in-depth security principles:

1. **Zero Data Leakage & Offline Inference**:
   All vector embeddings and LLM generations run entirely locally on the host machine. No user documents or reading history are transmitted to third-party cloud APIs.

2. **Filesystem Confinement & Traversal Guards**:
   All document reading and ingestion endpoints enforce alphanumeric pattern validation on IDs and enforce directory containment using `Path.is_relative_to(...)` to prevent `../` directory traversal attacks.

3. **Dynamic Cryptographic Entropy**:
   Application signing keys are auto-generated on first boot with 256 bits of cryptographic entropy (`secrets.token_urlsafe(32)`) and stored in restricted local storage (`data/.secret_key`).

4. **Stateless Authentication & Password Hashing**:
   User credentials are salted and hashed with `bcrypt`. API authorization utilizes stateless HS256 JWT tokens with strict expiration delta enforcement.

5. **Restricted CORS Policy**:
   Browser cross-origin resource sharing is restricted to localhost, local LAN address blocks, and authenticated reverse proxy tunnels.

---

## 🚨 Reporting a Vulnerability

If you discover a security vulnerability in Libre-Library, please do **NOT** open a public issue.

Instead, please report it via one of the following methods:
- **GitHub Security Advisory**: Submit a private report via the [GitHub Security Tab](https://github.com/K1ezy/Kieser-s-Libre-Library/security/advisories/new).
- **Direct Email**: Send details to `kieserleandro@gmail.com` with the subject line `[SECURITY] Libre-Library Vulnerability Report`.

Please include:
- A description of the vulnerability and its potential impact
- Step-by-step instructions or proof-of-concept to reproduce the behavior
- Any potential mitigations or suggested fixes

We will acknowledge your report within 48 hours and work with you to validate and release a patch promptly.
