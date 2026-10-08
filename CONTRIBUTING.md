# 🤝 Contributing to Libre-Library

Thank you for your interest in contributing to **Libre-Library**! As an offline-first, privacy-focused digital library and AI learning companion, contributions that improve performance, mobile usability, reader capabilities, and security are warmly welcome.

---

## 🧭 Table of Contents
1. [Code of Conduct](#-code-of-conduct)
2. [Development Setup](#-development-setup)
3. [Architecture & Coding Guidelines](#-architecture--coding-guidelines)
4. [Testing Guidelines](#-testing-guidelines)
5. [Git Workflow & Commit Conventions](#-git-workflow--commit-conventions)
6. [Submitting a Pull Request](#-submitting-a-pull-request)

---

## 🕊️ Code of Conduct
We are committed to providing a friendly, safe, and welcoming environment for all contributors. Please be respectful, constructive, and considerate in all interactions.

---

## 💻 Development Setup

### 1. Prerequisites
- **Python**: Version `3.11` or `3.12`
- **MongoDB**: Local or containerized instance (default connection: `mongodb://localhost:27017`)
- **Git**: Installed and configured

### 2. Clone and Setup Environment
```bash
# Clone the repository
git clone https://github.com/K1ezy/Kieser-s-Libre-Library.git
cd Kieser-s-Libre-Library

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# Upgrade pip and install dependencies
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

### 3. Model Weights Setup (Optional for Full AI Inference)
To run the local TARS AI assistant and flashcard generator:
```bash
python download_model.py
```
This downloads quantized GGUF weights into the `models/` directory.

### 4. Run the Development Server
```bash
python main.py
```
The application will launch locally at `http://localhost:8080`.

---

## 🏛️ Architecture & Coding Guidelines

### Core Principles
1. **Privacy-First & Zero Telemetry**: Never introduce external cloud AI calls or third-party telemetry. All inference must remain local.
2. **Asynchronous Non-Blocking Execution**: Use `async`/`await` for I/O operations with MongoDB (Motor) and offload CPU-bound or blocking disk reads using `run.io_bound(...)`.
3. **Coherent Light Aesthetic**: Follow the unified Slate 50 / Royal Indigo light design system in `ui/theme.py`. Avoid legacy `dark:` classes or intrusive dark mode toggles.
4. **Mobile Responsive Ergonomics**: Ensure all UI elements support mobile screens (compact 2-column filters, safe-area padding for bottom navigation docks, dynamic `100dvh` units).
5. **Path Confinement & Security**: Always sanitize file inputs and verify filesystem paths using `Path.is_relative_to(...)` and alphanumeric ID validation.

---

## 🧪 Testing Guidelines

Before committing or opening a PR, ensure all tests pass:

```bash
# Run all unit tests
python -m unittest discover tests

# Verify Python syntax and byte-compilation
python -m compileall core ui components tools tests
```

### Writing New Tests
- Place new unit tests in the `tests/` directory following the naming pattern `test_<module>.py`.
- Mock external hardware dependencies (like GPU or live LLM generation) where appropriate to keep the automated test suite fast and lightweight.

---

## 🌿 Git Workflow & Commit Conventions

We follow the **Conventional Commits** specification:

- `feat:` A new feature or user-facing capability
- `fix:` A bug fix or defect correction
- `docs:` Documentation-only changes (README, guides)
- `refactor:` Code changes that neither fix a bug nor add a feature
- `test:` Adding or updating automated tests
- `chore:` Maintenance tasks, dependency updates, CI workflows

### Example Commit Messages
```bash
feat(reader): add continuous scroll mode for PDF documents
fix(rag): handle empty metadata fields during document ingestion
docs: update OPDS catalog setup instructions
```

---

## 🚀 Submitting a Pull Request

1. Fork the repository and create your branch from `main`:
   ```bash
   git checkout -b feat/my-new-feature
   ```
2. Implement your changes following the coding and security guidelines.
3. Verify tests and byte compilation pass cleanly.
4. Push your branch to GitHub:
   ```bash
   git push origin feat/my-new-feature
   ```
5. Open a Pull Request against `main`. Fill out the [Pull Request Template](.github/pull_request_template.md) completely.
6. Check that the GitHub Actions CI workflow passes on your PR!
