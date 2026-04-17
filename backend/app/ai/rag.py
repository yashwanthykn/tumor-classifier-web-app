"""
app/ai/rag.py — RAG (Retrieval-Augmented Generation) Service

Singleton pattern: the SentenceTransformer model (~80MB) is loaded once
on first use, not on every request. ChromaDB is file-based and persistent
across container restarts via a Docker volume mounted at /app/data/chroma_db.

Usage:
    from app.ai.rag import rag_service

    # On startup (main.py lifespan)
    rag_service.initialize()

    # In agent.py — retrieve context for a user question
    chunks = rag_service.retrieve("What is glioblastoma?", top_k=3)
"""

import logging
import os
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────
CHROMA_DIR = os.getenv("CHROMA_DIR", "/app/data/chroma_db")
DOCS_DIR = os.getenv("MEDICAL_DOCS_DIR", "/app/data/medical_docs")
COLLECTION_NAME = "medical_knowledge"

# ── Chunking config ────────────────────────────────────────────────────
CHUNK_SIZE = 600        # characters (fits ~150 tokens, leaves room for context)
CHUNK_OVERLAP = 100     # character overlap between consecutive chunks
TOP_K_DEFAULT = 3

# ── Medical query keywords ─────────────────────────────────────────────
# Used by is_medical_query() to decide whether to run RAG.
# Data-oriented queries ("my scans", "my history") skip RAG entirely.
MEDICAL_KEYWORDS = {
    # Tumor types
    "glioma", "glioblastoma", "gbm", "meningioma", "pituitary", "adenoma",
    "astrocytoma", "oligodendroglioma", "ependymoma", "craniopharyngioma",
    "schwannoma", "medulloblastoma", "tumor", "tumour", "cancer", "malignant",
    "benign", "neoplasm", "lesion", "mass",
    # MRI & imaging
    "mri", "mri scan", "imaging", "gadolinium", "contrast", "t1", "t2", "flair",
    "diffusion", "perfusion", "spectroscopy", "enhancement",
    # Clinical terms
    "grade", "who grade", "biopsy", "resection", "surgery", "craniotomy",
    "radiation", "radiotherapy", "chemotherapy", "temozolomide", "bevacizumab",
    "idh", "mgmt", "methylation", "biomarker", "prognosis", "recurrence",
    # Symptoms
    "headache", "seizure", "nausea", "vomiting", "fatigue", "weakness",
    "cognitive", "memory", "vision", "speech", "coordination", "balance",
    # General medical education
    "treatment", "diagnosis", "symptom", "stage", "survival", "outlook",
    "what is", "explain", "tell me about", "describe", "how does", "why",
    "confidence score", "accuracy", "false positive", "false negative",
}


class RAGService:
    """
    Retrieval-Augmented Generation service.

    Lifecycle:
        1. Instantiated at module load (no heavy work yet).
        2. initialize() called in main.py lifespan — loads the embedding
           model and ingests any new documents.
        3. retrieve() called per request — fast vector search.
    """

    def __init__(self):
        self._embedding_model = None   # lazy-loaded SentenceTransformer
        self._chroma_client = None
        self._collection = None
        self._initialized = False

    # ══════════════════════════════════════════════════════════════════
    #  INITIALIZATION
    # ══════════════════════════════════════════════════════════════════

    def initialize(self) -> None:
        """
        Load the embedding model and connect to ChromaDB.
        Called once from main.py on app startup.
        Safe to call multiple times — idempotent.
        """
        if self._initialized:
            return

        logger.info("RAG: initializing...")

        try:
            self._load_embedding_model()
            self._connect_chroma()

            # Ingest documents if the collection is empty
            doc_count = self._collection.count()
            if doc_count == 0:
                logger.info("RAG: collection is empty — ingesting documents")
                self.ingest_documents(DOCS_DIR)
            else:
                logger.info(f"RAG: collection has {doc_count} chunks — skipping ingest")

            self._initialized = True
            logger.info("RAG: initialization complete")

        except Exception as e:
            # RAG failure must not crash the app — degrade gracefully
            logger.error(f"RAG: initialization failed: {e}", exc_info=True)

    def _load_embedding_model(self) -> None:
        """Load all-MiniLM-L6-v2 (~80MB). Called once."""
        from sentence_transformers import SentenceTransformer  # deferred import

        model_name = "sentence-transformers/all-MiniLM-L6-v2"
        logger.info(f"RAG: loading embedding model '{model_name}'...")
        self._embedding_model = SentenceTransformer(model_name)
        logger.info("RAG: embedding model loaded")

    def _connect_chroma(self) -> None:
        """Open (or create) the persistent ChromaDB collection."""
        import chromadb  # deferred import

        Path(CHROMA_DIR).mkdir(parents=True, exist_ok=True)
        self._chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
        self._collection = self._chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},  # cosine similarity
        )
        logger.info(f"RAG: connected to ChromaDB at '{CHROMA_DIR}'")

    # ══════════════════════════════════════════════════════════════════
    #  DOCUMENT INGESTION
    # ══════════════════════════════════════════════════════════════════

    def ingest_documents(self, docs_dir: str) -> int:
        """
        Load all .txt and .md files from docs_dir, chunk them, embed,
        and store in ChromaDB. Returns the number of chunks ingested.

        Idempotent by document filename: re-running will skip files whose
        IDs are already present (ChromaDB upsert semantics).
        """
        if not self._initialized and self._collection is None:
            raise RuntimeError("Call initialize() before ingest_documents()")

        docs_path = Path(docs_dir)
        if not docs_path.exists():
            logger.warning(f"RAG: docs directory '{docs_dir}' does not exist — skipping ingest")
            return 0

        files = list(docs_path.glob("*.md")) + list(docs_path.glob("*.txt"))
        if not files:
            logger.warning(f"RAG: no .md/.txt files found in '{docs_dir}'")
            return 0

        all_chunks: List[str] = []
        all_ids: List[str] = []
        all_metadata: List[dict] = []

        for file_path in sorted(files):
            try:
                text = file_path.read_text(encoding="utf-8").strip()
                if not text:
                    continue

                chunks = self._chunk_text(text)
                source = file_path.name

                for i, chunk in enumerate(chunks):
                    chunk_id = f"{source}::chunk_{i}"
                    all_chunks.append(chunk)
                    all_ids.append(chunk_id)
                    all_metadata.append({"source": source, "chunk_index": i})

                logger.info(f"RAG: '{source}' → {len(chunks)} chunks")

            except Exception as e:
                logger.error(f"RAG: failed to read '{file_path}': {e}")

        if not all_chunks:
            logger.warning("RAG: no content to ingest")
            return 0

        # Embed in batches of 64 to avoid memory spikes
        BATCH = 64
        for start in range(0, len(all_chunks), BATCH):
            batch_texts = all_chunks[start : start + BATCH]
            batch_ids = all_ids[start : start + BATCH]
            batch_meta = all_metadata[start : start + BATCH]

            embeddings = self._embed(batch_texts)

            self._collection.upsert(
                documents=batch_texts,
                embeddings=embeddings,
                ids=batch_ids,
                metadatas=batch_meta,
            )

        total = len(all_chunks)
        logger.info(f"RAG: ingested {total} chunks from {len(files)} files")
        return total

    def _chunk_text(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks of ~CHUNK_SIZE characters.
        Tries to break at paragraph boundaries first, then falls back to
        character-level splitting.
        """
        # Normalize whitespace but preserve paragraph breaks
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        chunks: List[str] = []
        current = ""

        for para in paragraphs:
            # If adding this paragraph keeps us under CHUNK_SIZE, append it
            candidate = (current + "\n\n" + para).strip() if current else para

            if len(candidate) <= CHUNK_SIZE:
                current = candidate
            else:
                # Flush current chunk (if any)
                if current:
                    chunks.append(current)

                # If the paragraph itself exceeds CHUNK_SIZE, hard-split it
                if len(para) > CHUNK_SIZE:
                    for i in range(0, len(para), CHUNK_SIZE - CHUNK_OVERLAP):
                        piece = para[i : i + CHUNK_SIZE]
                        if piece.strip():
                            chunks.append(piece.strip())
                    current = ""
                else:
                    current = para

        if current:
            chunks.append(current)

        return chunks

    # ══════════════════════════════════════════════════════════════════
    #  RETRIEVAL
    # ══════════════════════════════════════════════════════════════════

    def retrieve(self, query: str, top_k: int = TOP_K_DEFAULT) -> List[dict]:
        """
        Embed query → search ChromaDB → return top_k chunks.

        Returns a list of dicts:
            [{"text": "...", "source": "glioma.md", "score": 0.87}, ...]

        Returns [] if RAG is not initialized or collection is empty.
        Score is cosine similarity (higher = more relevant).
        """
        if not self._initialized or self._collection is None:
            logger.warning("RAG: retrieve() called but service is not initialized")
            return []

        if self._collection.count() == 0:
            return []

        try:
            query_embedding = self._embed([query])[0]

            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, self._collection.count()),
                include=["documents", "metadatas", "distances"],
            )

            chunks = []
            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            for doc, meta, dist in zip(documents, metadatas, distances):
                # ChromaDB cosine distance: 0 = identical, 2 = opposite
                # Convert to similarity score in [0, 1]
                similarity = round(1 - (dist / 2), 4)
                chunks.append({
                    "text": doc,
                    "source": meta.get("source", "unknown"),
                    "score": similarity,
                })

            # Filter out low-relevance chunks (similarity < 0.3)
            chunks = [c for c in chunks if c["score"] >= 0.3]

            logger.info(
                f"RAG: retrieved {len(chunks)} relevant chunks for query "
                f"(top score: {chunks[0]['score'] if chunks else 'n/a'})"
            )
            return chunks

        except Exception as e:
            logger.error(f"RAG: retrieve() failed: {e}", exc_info=True)
            return []

    # ══════════════════════════════════════════════════════════════════
    #  QUERY CLASSIFICATION
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def is_medical_query(message: str) -> bool:
        """
        Lightweight keyword check. Returns True if the message appears to be
        a medical/educational question that would benefit from RAG context.

        Returns False for data-oriented queries ("show my scans", "my history",
        "how many scans") — those use tools, not RAG.

        This is intentionally simple — a keyword hit on a ~50-word list is
        fast (microseconds) and good enough for this use case.
        """
        msg_lower = message.lower()

        # Explicit data-query signals → skip RAG
        data_signals = [
            "my scan", "my history", "my result", "my prediction",
            "how many scan", "show scan", "list scan", "scan #", "scan number",
            "last scan", "recent scan", "my statistics", "my stats",
        ]
        if any(sig in msg_lower for sig in data_signals):
            return False

        # Medical keyword hit → use RAG
        words = set(msg_lower.split())
        # Check single-word keywords
        if words & MEDICAL_KEYWORDS:
            return True
        # Check multi-word keywords (e.g. "what is", "tell me about")
        for kw in MEDICAL_KEYWORDS:
            if " " in kw and kw in msg_lower:
                return True

        return False

    # ══════════════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════════════

    def _embed(self, texts: List[str]) -> List[List[float]]:
        """Encode texts using the loaded SentenceTransformer model."""
        embeddings = self._embedding_model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def format_context_for_prompt(self, chunks: List[dict]) -> str:
        """
        Format retrieved chunks into a string block for injection into
        the system prompt.

        Example output:
            [Source: glioma.md]
            Glioblastoma (GBM) is the most aggressive...

            [Source: mri_interpretation.md]
            T2/FLAIR hyperintensity indicates...
        """
        if not chunks:
            return ""

        lines = []
        for chunk in chunks:
            lines.append(f"[Source: {chunk['source']}]")
            lines.append(chunk["text"])
            lines.append("")  # blank line separator

        return "\n".join(lines).strip()

    @property
    def is_ready(self) -> bool:
        """True if the service initialized successfully."""
        return self._initialized


# ── Module-level singleton ─────────────────────────────────────────────
# Import this instance everywhere. Do NOT create new RAGService() instances.
rag_service = RAGService()