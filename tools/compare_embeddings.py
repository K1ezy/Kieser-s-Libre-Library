import time
import os
import sys
from pathlib import Path
import numpy as np

# Ensure stdout handles UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"

print("=" * 75)
print("  LIBRE-LIBRARY: EMBEDDING BENCHMARK")
print("  all-MiniLM-L6-v2  VS  BAAI/bge-small-en-v1.5")
print("=" * 75)

try:
    from sentence_transformers import SentenceTransformer, util
    import chromadb
    from chromadb.config import Settings
except ImportError as e:
    print(f"Missing dependency: {e}")
    sys.exit(1)

# 1. Load / Prepare Models
minilm_path = MODELS_DIR / "all-MiniLM-L6-v2"
minilm_target = str(minilm_path) if minilm_path.exists() else "all-MiniLM-L6-v2"
bge_target = "BAAI/bge-small-en-v1.5"

print(f"\n[1/4] Loading models onto CPU...")
t0 = time.time()
print(f"  • Loading all-MiniLM-L6-v2 from: {minilm_target}")
model_minilm = SentenceTransformer(minilm_target, device="cpu")
t_minilm = time.time() - t0
print(f"    Loaded in {t_minilm:.2f}s | Dim: {model_minilm.get_sentence_embedding_dimension()} | Params: ~{sum(p.numel() for p in model_minilm.parameters()):,}")

t0 = time.time()
print(f"  • Loading BAAI/bge-small-en-v1.5 (downloading if not cached)...")
model_bge = SentenceTransformer(bge_target, device="cpu")
t_bge = time.time() - t0
print(f"    Loaded in {t_bge:.2f}s | Dim: {model_bge.get_sentence_embedding_dimension()} | Params: ~{sum(p.numel() for p in model_bge.parameters()):,}")

# 2. Benchmark Speed & Throughput
print("\n" + "=" * 75)
print("[2/4] Speed & Latency Benchmark (Single CPU)")
print("=" * 75)

sample_query = "How does the library safeguard student reading privacy under Philippine law?"
sample_passages = [
    f"Passage {i}: North Eastern Mindanao State University implements institutional policy FM-LIBS-{i:03d} to regulate digital reading access, ensuring that research records and attendance metrics are securely preserved on local university servers."
    for i in range(30)
]

# Warmup
_ = model_minilm.encode([sample_query], convert_to_tensor=True)
_ = model_bge.encode([sample_query], convert_to_tensor=True)

# Query Latency (10 iterations)
minilm_query_times = []
for _ in range(10):
    t_start = time.perf_counter()
    _ = model_minilm.encode(sample_query, convert_to_tensor=True)
    minilm_query_times.append(time.perf_counter() - t_start)
minilm_q_avg = np.mean(minilm_query_times) * 1000

bge_query_times = []
bge_instruction_query = f"Represent this sentence for searching relevant passages: {sample_query}"
for _ in range(10):
    t_start = time.perf_counter()
    _ = model_bge.encode(bge_instruction_query, convert_to_tensor=True)
    bge_query_times.append(time.perf_counter() - t_start)
bge_q_avg = np.mean(bge_query_times) * 1000

# Passage Batch Ingestion Throughput (30 passages)
t_start = time.perf_counter()
_ = model_minilm.encode(sample_passages, batch_size=16, convert_to_tensor=True)
minilm_batch_time = time.perf_counter() - t_start
minilm_thru = len(sample_passages) / minilm_batch_time

t_start = time.perf_counter()
_ = model_bge.encode(sample_passages, batch_size=16, convert_to_tensor=True)
bge_batch_time = time.perf_counter() - t_start
bge_thru = len(sample_passages) / bge_batch_time

print(f"{'Metric':<35} | {'all-MiniLM-L6-v2':<18} | {'BAAI/bge-small-en-v1.5':<22}")
print("-" * 80)
print(f"{'Single Query Latency (avg)':<35} | {minilm_q_avg:6.2f} ms         | {bge_q_avg:6.2f} ms")
print(f"{'Batch Ingestion (30 chunks)':<35} | {minilm_batch_time:6.2f} s          | {bge_batch_time:6.2f} s")
print(f"{'Throughput (chunks/second)':<35} | {minilm_thru:6.1f} chunks/s    | {bge_thru:6.1f} chunks/s")

# 3. Semantic Discrimination Test (True Positive vs Hard Negative vs Distractor)
print("\n" + "=" * 75)
print("[3/4] Semantic Discrimination & Contrastive Precision Test")
print("=" * 75)

test_scenarios = [
    {
        "title": "Scenario A: Data Privacy (Abstract paraphrase vs Keyword trap)",
        "query": "How does the system protect student research confidentiality without cloud exposure?",
        "bge_query": "Represent this sentence for searching relevant passages: How does the system protect student research confidentiality without cloud exposure?",
        "target": "Under RA 10173 data privacy mandates, all thesis drafts and student logs reside strictly on local campus servers without outbound API transit.",
        "hard_neg": "Third-party cloud storage vendors provide student backup systems with encrypted cloud synchronization across multiple public servers.",
        "distractor": "The library entrance requires students to tap their university RFID identification card on the doorway reader."
    },
    {
        "title": "Scenario B: Computer Science (Deadlock resolution vs UI freeze)",
        "query": "How to resolve deadlocks in multi-threaded concurrency",
        "bge_query": "Represent this sentence for searching relevant passages: How to resolve deadlocks in multi-threaded concurrency",
        "target": "Deadlock conditions such as circular wait and hold-and-wait can be prevented by establishing a global resource ordering hierarchy.",
        "hard_neg": "The application user interface froze during database export because long-running tasks blocked the main thread event loop.",
        "distractor": "Relational databases use B-Tree indices to accelerate indexed select queries on primary keys."
    },
    {
        "title": "Scenario C: Copyright & DRM (Read-only policy vs File download)",
        "query": "Copyright policies regarding student access to electronic books",
        "bge_query": "Represent this sentence for searching relevant passages: Copyright policies regarding student access to electronic books",
        "target": "In accordance with RA 8293, students are restricted to in-browser reading without raw document downloading to prevent unauthorized distribution.",
        "hard_neg": "Students can download free open-source software tools from the computer laboratory server using local network file shares.",
        "distractor": "Faculty members submit book requisition requests using standard form FM-LIBS-002 for semi-annual procurement."
    }
]

for sc in test_scenarios:
    print(f"\n--- {sc['title']} ---")
    print(f"Query: \"{sc['query']}\"")
    
    # MiniLM Cosine Similarities
    q_emb_m = model_minilm.encode(sc['query'], convert_to_tensor=True)
    t_emb_m = model_minilm.encode(sc['target'], convert_to_tensor=True)
    hn_emb_m = model_minilm.encode(sc['hard_neg'], convert_to_tensor=True)
    d_emb_m = model_minilm.encode(sc['distractor'], convert_to_tensor=True)
    
    sim_m_target = float(util.cos_sim(q_emb_m, t_emb_m)[0][0])
    sim_m_hn = float(util.cos_sim(q_emb_m, hn_emb_m)[0][0])
    sim_m_d = float(util.cos_sim(q_emb_m, d_emb_m)[0][0])
    margin_m = sim_m_target - sim_m_hn
    
    # BGE Cosine Similarities
    q_emb_b = model_bge.encode(sc['bge_query'], convert_to_tensor=True)
    t_emb_b = model_bge.encode(sc['target'], convert_to_tensor=True)
    hn_emb_b = model_bge.encode(sc['hard_neg'], convert_to_tensor=True)
    d_emb_b = model_bge.encode(sc['distractor'], convert_to_tensor=True)
    
    sim_b_target = float(util.cos_sim(q_emb_b, t_emb_b)[0][0])
    sim_b_hn = float(util.cos_sim(q_emb_b, hn_emb_b)[0][0])
    sim_b_d = float(util.cos_sim(q_emb_b, d_emb_b)[0][0])
    margin_b = sim_b_target - sim_b_hn
    
    print(f"{'Target (True Positive)':<28} | MiniLM: {sim_m_target:+.4f} | BGE: {sim_b_target:+.4f}")
    print(f"{'Hard Negative (Trap)':<28} | MiniLM: {sim_m_hn:+.4f} | BGE: {sim_b_hn:+.4f}")
    print(f"{'Distractor (Irrelevant)':<28} | MiniLM: {sim_m_d:+.4f} | BGE: {sim_b_d:+.4f}")
    winner = "BGE v1.5 (+)" if margin_b > margin_m else "MiniLM (+)"
    print(f"-> Discrimination Margin (Target - Trap): MiniLM = {margin_m:+.4f} | BGE = {margin_b:+.4f} => Winner: {winner}")

# 4. Realistic ChromaDB Vector Retrieval Benchmark
print("\n" + "=" * 75)
print("[4/4] Realistic ChromaDB Retrieval Simulation (20 Diverse Library Documents)")
print("=" * 75)

corpus = [
    # 0
    "Agile Software Development relies on iterative sprint cycles, daily standups, and adaptive planning rather than rigid waterfall phases.",
    # 1
    "Under the Philippine Data Privacy Act of 2012 (RA 10173), personal sensitive information must be processed with informed consent and stored securely.",
    # 2
    "The Intellectual Property Code of the Philippines (RA 8293) safeguards copyright holders by prohibiting unauthorized reproduction and transmission of literary works.",
    # 3
    "Third Normal Form (3NF) in relational database design requires that all transitive dependencies are eliminated and every non-prime attribute is fully functionally dependent on the primary key.",
    # 4
    "Boyce-Codd Normal Form (BCNF) is a stricter variant of 3NF where for every non-trivial functional dependency X -> Y, X must be a superkey.",
    # 5
    "Deadlock detection algorithms utilize resource allocation graphs (RAG) to locate cycles indicating circular waiting among competing processes.",
    # 6
    "Virtual memory management employs paging and translation lookaside buffers (TLB) to map virtual addresses to physical RAM frames.",
    # 7
    "NiceGUI is a Python-based UI framework built on top of FastAPI, Vue.js, and Quasar that enables real-time web application development without writing JavaScript.",
    # 8
    "ChromaDB is an open-source embedding database designed to store document vectors, page metadata, and execute approximate nearest neighbor search using HNSW indexing.",
    # 9
    "TARS AI Librarian utilizes Retrieval-Augmented Generation (RAG) to extract factual book excerpts and provide them as grounded prompt context to an offline LLM.",
    # 10
    "Doorway QR code attendance logging automates entrance tracking and eliminates student queues at university library reception gates.",
    # 11
    "FM-LIBS-009 is the official NEMSU ISO institutional logbook form recording student ID, name, college, year level, time in, and time out.",
    # 12
    "FM-LIBS-002 represents the university library requisition request form used by faculty to request procurement of books, journal subscriptions, and learning resources.",
    # 13
    "Convolutional Neural Networks (CNN) utilize spatial kernel convolutions, pooling layers, and rectified linear activation units for computer vision analysis.",
    # 14
    "Transformer models leverage multi-head self-attention mechanisms to model contextual relationships across sequence tokens without recurrence.",
    # 15
    "The Model-View-Controller (MVC) architectural pattern decouples domain logic, user presentation, and incoming input commands into distinct layers.",
    # 16
    "Bcrypt password hashing incorporates a salt and adjustable cost factor to defend user credentials against brute-force rainbow table attacks.",
    # 17
    "JSON Web Tokens (JWT) consist of a base64url-encoded header, payload, and HMAC-SHA256 signature providing stateless cryptographic authentication.",
    # 18
    "Rapid Application Development (RAD) prioritizes rapid prototyping, iterative user feedback, and software component reuse over lengthy specification writing.",
    # 19
    "OPDS (Open Publication Distribution System) 1.2 is an Atom XML syndication standard that enables e-readers to browse and sync digital library catalogs wirelessly."
]

benchmark_queries = [
    {
        "q": "What form is used for faculty book purchase requisitions?",
        "bge_q": "Represent this sentence for searching relevant passages: What form is used for faculty book purchase requisitions?",
        "expected_idx": 12,
        "topic": "Institutional Requisition Form"
    },
    {
        "q": "How does RAG provide factual context to language models?",
        "bge_q": "Represent this sentence for searching relevant passages: How does RAG provide factual context to language models?",
        "expected_idx": 9,
        "topic": "TARS AI & RAG Engine"
    },
    {
        "q": "Which Philippine law regulates student data privacy and local storage?",
        "bge_q": "Represent this sentence for searching relevant passages: Which Philippine law regulates student data privacy and local storage?",
        "expected_idx": 1,
        "topic": "Data Privacy (RA 10173)"
    },
    {
        "q": "Eliminating transitive dependencies in relational database schemas",
        "bge_q": "Represent this sentence for searching relevant passages: Eliminating transitive dependencies in relational database schemas",
        "expected_idx": 3,
        "topic": "Database Normalization 3NF"
    },
    {
        "q": "Protocol for syndicating electronic book catalogs to mobile reading apps",
        "bge_q": "Represent this sentence for searching relevant passages: Protocol for syndicating electronic book catalogs to mobile reading apps",
        "expected_idx": 19,
        "topic": "OPDS E-Reader Feed"
    }
]

# Create Ephemeral ChromaDB collections for each
client = chromadb.Client(Settings(anonymized_telemetry=False, is_persistent=False))

# MiniLM Collection
col_minilm = client.create_collection("eval_minilm")
col_minilm.add(
    documents=corpus,
    embeddings=[model_minilm.encode(doc).tolist() for doc in corpus],
    ids=[f"doc_{i}" for i in range(len(corpus))]
)

# BGE Collection
col_bge = client.create_collection("eval_bge")
col_bge.add(
    documents=corpus,
    embeddings=[model_bge.encode(doc).tolist() for doc in corpus],
    ids=[f"doc_{i}" for i in range(len(corpus))]
)

print(f"{'Query Topic':<30} | {'Expected':<8} | {'MiniLM Top-1 (Distance)':<22} | {'BGE Top-1 (Distance)':<22}")
print("-" * 90)

minilm_top1_correct = 0
bge_top1_correct = 0

for bq in benchmark_queries:
    # Query MiniLM
    q_emb_m = model_minilm.encode([bq['q']]).tolist()
    res_m = col_minilm.query(query_embeddings=q_emb_m, n_results=3)
    top1_m_id = res_m['ids'][0][0]
    top1_m_idx = int(top1_m_id.split('_')[1])
    dist_m = res_m['distances'][0][0]
    is_m_correct = (top1_m_idx == bq['expected_idx'])
    if is_m_correct:
        minilm_top1_correct += 1
    
    # Query BGE
    q_emb_b = model_bge.encode([bq['bge_q']]).tolist()
    res_b = col_bge.query(query_embeddings=q_emb_b, n_results=3)
    top1_b_id = res_b['ids'][0][0]
    top1_b_idx = int(top1_b_id.split('_')[1])
    dist_b = res_b['distances'][0][0]
    is_b_correct = (top1_b_idx == bq['expected_idx'])
    if is_b_correct:
        bge_top1_correct += 1
    
    m_status = f"doc_{top1_m_idx} ({dist_m:.3f}) {'✓' if is_m_correct else '✗'}"
    b_status = f"doc_{top1_b_idx} ({dist_b:.3f}) {'✓' if is_b_correct else '✗'}"
    print(f"{bq['topic']:<30} | doc_{bq['expected_idx']:<4} | {m_status:<22} | {b_status:<22}")

print("\n" + "=" * 75)
print(f"FINAL SCORE (Top-1 Retrieval Accuracy):")
print(f"  • all-MiniLM-L6-v2:      {minilm_top1_correct} / {len(benchmark_queries)} ({(minilm_top1_correct/len(benchmark_queries))*100:.1f}%)")
print(f"  • BAAI/bge-small-en-v1.5: {bge_top1_correct} / {len(benchmark_queries)} ({(bge_top1_correct/len(benchmark_queries))*100:.1f}%)")
print("=" * 75)
