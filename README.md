# 📚 Libre-Library

> **Intelligent, AI-Powered Personal Digital Library, E-Reader & Study Hub**  
> Built with **Python**, **NiceGUI** (Vue/Quasar/Tailwind), **MongoDB**, **ChromaDB**, and **Local LLMs** (Llama 3.2 / RAG).

---

## 🌟 Overview

**Libre-Library** is a modern, self-hosted personal digital library and learning assistant. It combines a clean, mobile-optimized digital reading interface with local Retrieval-Augmented Generation (RAG) AI capabilities. Users can organize, read, search, summarize, and study their books and research documents offline with zero data leakage.

Whether accessed on a desktop workstation or on a mobile phone via local network or secure tunnels (ngrok), Libre-Library delivers a fluid, responsive, and distraction-free experience.

---

## ✨ Key Features

### 🤖 Local AI & RAG Engine (TARS Assistant)
- **Zero-Cloud Privacy**: Powered by local quantized models (default: `Llama-3.2-3B-Instruct-Q8_0.gguf`) running on GPU/CPU via `llama-cpp-python`.
- **Retrieval-Augmented Generation (RAG)**: Integrates ChromaDB vector storage and HuggingFace Sentence Transformers (`all-MiniLM-L6-v2`) to query and chat with your entire document collection with precise source citations.
- **Contextual Ingestion**: Automatically chunks, embeds, and indexes PDFs, EPUBs, TXT, and Markdown files.
- **Persistent Chat Sessions**: Dedicated conversation history, multi-session management, and floating quick-chat widget available on any page.

### 📖 Universal Digital E-Reader
- **Multi-Format Support**: Native reader for EPUB and PDF documents.
- **Responsive Layout**: Full-bleed reading view, adjustable typography, dark/light themes, and mobile-friendly navigation.
- **Seamless Metadata Extraction**: Automatically parses covers, authors, summaries, and publication details.

### 📑 Smart Document Ingestion & Summarizer
- **Drag-and-Drop Ingestion Hub**: Upload and process single or multi-volume books and lecture slides.
- **Automated Summaries**: Generates high-yield chapter summaries, key takeaways, and core concept breakdowns.
- **Metadata Enrichment**: Built-in tools for synchronizing book synopses, authors, and cover art.

### 📅 Active Study Planner & Flashcards
- **Interactive Task Calendar**: Track study tasks, due dates, reading goals, and milestones.
- **Flashcard Decks**: Automatically generated and custom study decks with responsive carousel cards for active recall.
- **Real-time Status Tracking**: Toggle task completion with instant synchronization to MongoDB.

### 📱 Mobile-First Responsive Design
- **Engineered for Mobile Screens**: Specially optimized for 320px–430px smartphone viewports (iPhone, Android) up to 4K displays.
- **Persistent Bottom Navigation Bar**: Quick mobile navigation across Home, Books, Chat, Planner, and Profile.
- **Touch-Optimized UI**: 44px+ minimum touch targets, collapsible sidebars, non-overlapping floating action buttons, and iOS auto-zoom prevention (`font-size: 16px`).

### 🔐 Security & User Management
- **Role-Based Access Control**: Multi-user support with `admin` and `user` tiers. The first registered user is automatically designated as **Admin**.
- **Modern Authentication**: Secure password hashing with `bcrypt` and stateless JWT session management via HTTP-only NiceGUI storage.
- **Case-Insensitive & Sanitized Auth**: Normalizes usernames and emails, preventing duplicates and whitespace errors.

---

## 🛠️ Architecture & Tech Stack

```
┌─────────────────────────────────────────────────────────────┐
│                    User Interface (NiceGUI)                 │
│         Vue 3 / Quasar / TailwindCSS / Theme System         │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                  Application Layer (FastAPI)                │
│         Routing / JWT Auth Guard / Session Management       │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
┌──────────────▼──────────────┐ ┌──────────────▼──────────────┐
│      Database & Storage     │ │          AI / RAG Core      │
│  - MongoDB (Motor Async)    │ │  - llama-cpp-python (Llama) │
│  - Document & User Data     │ │  - ChromaDB Vector Store    │
│  - Task / Study Planner     │ │  - SentenceTransformers     │
└─────────────────────────────┘ └─────────────────────────────┘
```

- **Frontend & App Framework**: [NiceGUI](https://nicegui.io/) (FastAPI + Quasar + Vue 3 + Tailwind CSS)
- **Primary Database**: MongoDB (asynchronous driver via `motor`)
- **Vector Database**: [ChromaDB](https://www.trychroma.com/) for document embeddings and semantic search
- **Embeddings Model**: `sentence-transformers/all-MiniLM-L6-v2`
- **LLM Runtime**: `llama-cpp-python` (with GPU CUDA offloading support)
- **Authentication**: Passlib / Bcrypt + PyJWT
- **Public Tunneling**: Ngrok integration for remote access

---

## 📂 Project Directory Structure

```plaintext
Libre-Library/
├── assets/                  # App images, logos, and UI assets
├── components/              # Reusable UI components
│   ├── book_card.py         # Responsive book display card
│   ├── bottom_nav.py        # Mobile bottom navigation bar
│   ├── chat_floating.py     # Floating action button & quick-chat modal
│   ├── header.py            # Responsive top header & search dialog
│   └── sidebar.py           # Collapsible navigation drawer
├── core/                    # Core backend logic & services
│   ├── ai_engine/           # LLM & RAG retrieval pipelines
│   │   ├── llm_engine.py    # Local Llama-3.2 runner & streaming
│   │   └── rag_pipeline.py  # ChromaDB semantic query & context injection
│   ├── auth/                # JWT handler & session helpers
│   ├── database/            # MongoDB connection & schema managers
│   │   └── mongo_manager.py # Motor asynchronous MongoDB repository
│   ├── external_api/        # Book API integrations (dBooks, etc.)
│   ├── library/             # Book scanner & file system watchers
│   ├── services/            # Ingestion & document chunking services
│   └── utils/               # Text extractors (PDF, EPUB, TXT, MD)
├── data/                    # App data directory (books, metadata, vectors)
│   ├── books/               # Organized book folders & metadata.json
│   └── chroma_db/           # Chroma vector database indices
├── E-Books/                 # Raw/incoming electronic books directory
├── models/                  # Local LLM weights (.gguf files)
├── static/                  # Static assets & EPUB.js web reader
├── tools/                   # Maintenance & administrative CLI scripts
│   ├── fix_authors.py       # Metadata author cleaning
│   └── manage_users.py      # User account listing & deletion utility
├── ui/                      # UI pages & styling
│   ├── pages/               # Main application pages
│   │   ├── admin.py         # Admin control panel
│   │   ├── auth.py          # Login & registration screens
│   │   ├── book_collection.py# Book catalog & search filter
│   │   ├── book_details.py  # Book detail view & actions
│   │   ├── chat.py          # Full-page AI chat assistant
│   │   ├── home.py          # Dashboard, reading stats, hero
│   │   ├── planner.py       # Study planner, calendar & flashcards
│   │   ├── profile.py       # User profile management
│   │   ├── reader_interface.py# E-reader interface
│   │   ├── summarizer.py    # AI book/chapter summarizer
│   │   └── upload.py        # Ingestion Hub file uploader
│   └── theme.py             # Global typography, color tokens, CSS rules
├── cleanup_bad_data.py      # Cleans corrupted/placeholder book metadata
├── download_model.py        # Automated GGUF model downloader
├── main.py                  # Application entry point & route definitions
├── requirements.txt         # Python package dependencies
└── start_app.bat            # One-click Windows startup & ngrok launcher
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python**: Version 3.11 or 3.12 (recommended)
- **MongoDB Community Server**: Running locally on port `27017`
- **Git**: Installed and configured
- *(Optional)* **NVIDIA GPU with CUDA**: For high-speed LLM inference

### 2. Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/K1ezy/Kieser-s-Libre-Library.git
   cd Libre-Library
   ```

2. **Create and activate a virtual environment**:
   ```bash
   # Windows
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Download the local AI model**:
   ```bash
   python download_model.py
   ```
   *Downloads `Llama-3.2-3B-Instruct-Q8_0.gguf` into the `models/` directory.*

5. **Verify MongoDB**:
   Ensure MongoDB service is running:
   ```bash
   net start MongoDB
   ```

---

## 🖥️ Running the Application

### Option A: One-Click Startup (Recommended for Windows)
Double-click `start_app.bat` or run:
```bash
start_app.bat
```
*This automatically starts the Libre-Library server on port `8080` and initializes an `ngrok` tunnel for remote mobile access.*

### Option B: Manual Command Line
```bash
python main.py
```
- **Local Access**: Open `http://localhost:8080` in your browser.
- **First-Time Login**: Head to `/signup` to register. The first user created automatically receives **Administrator** privileges!

---

## ⚙️ Configuration (`core/config.py`)

Configuration values can be overridden via environment variables or a `.env` file:

| Variable | Default Value | Description |
|---|---|---|
| `PROJECT_NAME` | `Libre Library` | Application title |
| `MONGO_URI` | `mongodb://localhost:27017` | MongoDB connection URI |
| `DB_NAME` | `libre_library_db` | Primary database name |
| `SECRET_KEY` | `libre_library_secure_key_2025` | Session cookie encryption secret |
| `JWT_SECRET` | `libre_library_secure_key_2025` | JWT token signing key |
| `ACCESS_TOKEN_EXPIRE_MINUTES`| `1440` (24h) | Access token expiration |
| `MODEL_FILENAME` | `Llama-3.2-3B-Instruct-Q8_0.gguf` | AI Model filename in `models/` |
| `GPU_LAYERS` | `20` | Layers offloaded to GPU (`-1` for full) |
| `CONTEXT_WINDOW` | `8192` | LLM context window size |

---

## 🛠️ CLI Management Utilities

### User & Credential Management
A dedicated CLI tool is provided at `tools/manage_users.py` to inspect or reset registered users:

```bash
# List all registered user accounts and roles:
python tools/manage_users.py list

# Delete all user accounts & credentials (resets database for new admin signup):
python tools/manage_users.py delete
```

### Library Data Maintenance
```bash
# Scan and clean corrupted/placeholder metadata:
python cleanup_bad_data.py

# Fix and normalize author fields across books:
python tools/fix_authors.py

# Re-index and enrich library book metadata:
python smart_librarian.py
```

---

## 📋 Changelog & Updates (Implemented Today - Sept 13, 2026)

### 1. 🚀 Codebase Overhaul & Async MongoDB Migration
- Converted database interaction across all services to asynchronous `Motor` operations, eliminating event-loop stalls.
- Optimized query indexes for users, books, and planner tasks.

### 2. 🔐 Authentication System & Normalization Fixes
- **Whitespace & Case Normalization**: Fixed registration and login edge-cases where trailing spaces or inconsistent casing locked users out.
- **Duplicate Account Reconciliation**: Added `normalize_existing_users()` to merge duplicate account records.
- **First-User Admin Provisioning**: Built automated admin role assignment for the initial registered user.

### 3. 🤖 TARS AI Engine & Ingestion Hub Fixes
- **Engine Online Status**: Resolved offline status indicator for TARS by adding model validation checks and fallback logic.
- **Ingestion Hub Parsing**: Fixed file uploading issues by rewriting `core/utils/text_extractor.py` to reliably extract text from PDFs, EPUBs, and plain text files.
- **RAG Query Accuracy**: Improved prompt synthesis and chunk scoring for academic papers, lecture slides, and technical documents.

### 4. 📦 Repository Size Optimization
- Cleaned redundant 10.5 GB build artifacts, stale virtual environment duplicates, and heavy model caches.
- Configured `.gitignore` to protect source control from model weights (`*.gguf`), local databases, and temporary logs.

### 5. 📱 Comprehensive Mobile-First UI/UX Overhaul
- **Global Theme & Viewport**:
  - Added mobile viewport tags with `viewport-fit=cover`.
  - Added CSS safe-area variables (`env(safe-area-inset-*)`).
  - Added horizontal scroll locking (`overflow-x: hidden`) and touch momentum scrolling.
  - Implemented iOS auto-zoom prevention by enforcing `font-size: 16px` on form inputs.
- **Mobile Bottom Navigation Bar**:
  - Created [components/bottom_nav.py](file:///c:/Users/User/Desktop/Libre-Library/components/bottom_nav.py) with active destination highlighting (`/`, `/books`, `/chat`, `/planner`, `/profile`).
- **Pages Optimized Across All Screen Sizes (320px–430px up to Desktop)**:
  - **Home**: Adaptive hero banner, dynamic stat tiles, responsive book shelf.
  - **Book Collection**: Collapsible 2-column mobile filters, touch-friendly book action buttons.
  - **Book Details**: Centered responsive book cover, wrapped genre chips, and non-overlapping action buttons.
  - **Reader Interface**: Truncated document header titles to prevent action button overflow.
  - **Chat**: Redesigned 2-row sticky input bar (quick actions above, input below) and responsive chat bubbles.
  - **Study Planner**: Responsive calendar sizing, connected drawer toggles, and responsive flashcard carousels.
  - **Summarizer**: Fluid summary containers with clean word wrapping.
  - **Upload**: Single-column mobile layout for document ingestion.
  - **Profile**: Responsive avatar card and user statistics grid.
  - **Admin**: Horizontally scrollable data tables and responsive management tools.

### 6. 🧹 Database User Wipe & Reset
- Successfully cleared 17 test account credentials and 26 orphaned planner tasks from MongoDB.
- Verified zero collision state, allowing fresh registration of the primary Administrator account.

### 7. ⚡ UI Navigation Fix (`LeftDrawer`)
- Replaced `drawer.close` with `drawer.hide` in [components/sidebar.py](file:///c:/Users/User/Desktop/Libre-Library/components/sidebar.py), resolving Quasar `LeftDrawer` AttributeError on mobile drawer toggle.
- Reconciled MongoDB sparse indexes on `users` collection (`email_1`, `username_1`), removing startup index conflicts.

### 8. 🧠 Study Planner & Flashcard Generation Overhaul
- **Resolved `delete_deck_by_task` Bug**: Added alias mapping to `delete_deck(task_id)` in [ui/pages/planner_service.py](file:///c:/Users/User/Desktop/Libre-Library/ui/pages/planner_service.py) and added safe try/except wrappers in [ui/pages/planner.py](file:///c:/Users/User/Desktop/Libre-Library/ui/pages/planner.py).
- **Eliminated White-Screen / Modal Freeze**: Removed nested spinner dialogs that conflicted with Quasar backdrops. Progress feedback is now rendered directly in-place within the study modal.
- **Fast, High-Yield Generation**: Re-architected chunking to focus on the top 2 informative document sections with a 1,000-token prompt, reducing generation time from 15+ minutes down to **10–25 seconds**.
- **Universal Multi-Format File Reader**: Robustly parses NiceGUI `FileUpload`, `UploadEventArguments`, library book paths, and raw bytes with immediate file-handle release on Windows.
- **Graceful Error Recovery**: Added in-place "Try Another Document" retry card for empty or unsupported files.

### 9. 🔄 Git Repository Synchronization
- Synchronized all codebase improvements and documentation directly to GitHub (`main` branch).

---

## 📜 License

This project is licensed under the **MIT License**. Free for personal and educational use.
