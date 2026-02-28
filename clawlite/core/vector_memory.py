"""
ClawLite Vector Memory — Busca semântica via embeddings.

Suporta múltiplos backends de embedding:
- OpenAI text-embedding-3-small (cloud)
- Sentence-Transformers all-MiniLM-L6-v2 (local, opcional)
- Fallback para busca por keywords quando sem embeddings

Armazena vetores em SQLite com operações de similaridade por cosseno.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from clawlite.config import settings as app_settings

logger = logging.getLogger(__name__)

def _db_dir() -> Path:
    return Path(app_settings.CONFIG_DIR)


def _vector_db_path() -> Path:
    return _db_dir() / "vector_memory.db"

# Configuração de chunking
DEFAULT_CHUNK_SIZE = 400       # tokens por chunk
DEFAULT_CHUNK_OVERLAP = 80     # tokens de sobreposição
EMBEDDING_DIM = 1536           # OpenAI text-embedding-3-small


@dataclass
class MemoryChunk:
    """Um pedaço de memória com embedding."""
    id: str
    text: str
    source: str
    embedding: list[float] = field(default_factory=list)
    created_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """Resultado de busca semântica."""
    text: str
    source: str
    score: float
    chunk_id: str = ""


def _conn() -> sqlite3.Connection:
    db_path = _vector_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    return conn


def init_vector_db() -> None:
    """Cria as tabelas de memória vetorial."""
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT '',
                embedding TEXT NOT NULL DEFAULT '[]',
                created_at REAL NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source)
        """)


def _chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    """Divide texto em chunks com sobreposição."""
    words = text.split()
    if len(words) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size - overlap
        if start >= len(words):
            break

    return chunks


def _compute_embedding_openai(texts: list[str], api_key: str) -> list[list[float]]:
    """Computa embeddings via OpenAI API."""
    url = "https://api.openai.com/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "text-embedding-3-small",
        "input": texts,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return [item["embedding"] for item in data["data"]]
    except Exception as e:
        logger.warning("OpenAI embedding failed: %s", e)
        return []


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Similaridade de cosseno entre dois vetores."""
    if len(a) != len(b) or not a:
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


def _keyword_score(query: str, text: str) -> float:
    """BM25-simplificado: pontuação por keywords."""
    query_words = set(w.lower() for w in query.split() if len(w) > 2)
    text_lower = text.lower()
    if not query_words:
        return 0.0

    hits = sum(1 for w in query_words if w in text_lower)
    return hits / len(query_words)


def store_memory(
    text: str,
    source: str = "manual",
    metadata: dict[str, Any] | None = None,
    api_key: str = "",
) -> int:
    """Armazena texto na memória vetorial, chunking + embedding."""
    init_vector_db()

    chunks = _chunk_text(text)
    embeddings: list[list[float]] = []

    # Tenta computar embeddings se tem API key
    resolved_key = api_key or os.getenv("OPENAI_API_KEY", "").strip()
    if resolved_key and chunks:
        embeddings = _compute_embedding_openai(chunks, resolved_key)

    # Pad com vetores vazios se embedding falhou
    while len(embeddings) < len(chunks):
        embeddings.append([])

    stored = 0
    now = time.time()

    with _conn() as c:
        for chunk_text, embedding in zip(chunks, embeddings):
            chunk_id = hashlib.sha256(f"{source}:{chunk_text[:200]}".encode()).hexdigest()[:16]

            c.execute("""
                INSERT OR REPLACE INTO chunks (id, text, source, embedding, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                chunk_id,
                chunk_text,
                source,
                json.dumps(embedding),
                now,
                json.dumps(metadata or {}),
            ))
            stored += 1

    logger.info("Stored %d chunks from source '%s'", stored, source)
    return stored


def search_memory(
    query: str,
    max_results: int = 6,
    min_score: float = 0.25,
    vector_weight: float = 0.7,
    keyword_weight: float = 0.3,
    api_key: str = "",
) -> list[SearchResult]:
    """
    Busca híbrida: combina similaridade vetorial com BM25 por keywords.
    Se não há embeddings, faz fallback para keyword-only.
    """
    init_vector_db()

    resolved_key = api_key or os.getenv("OPENAI_API_KEY", "").strip()

    # Computa embedding da query
    query_embedding: list[float] = []
    if resolved_key:
        result = _compute_embedding_openai([query], resolved_key)
        if result:
            query_embedding = result[0]

    with _conn() as c:
        rows = c.execute("SELECT id, text, source, embedding, created_at FROM chunks").fetchall()

    if not rows:
        return []

    scored: list[tuple[float, SearchResult]] = []

    for row in rows:
        text = row["text"]
        source = row["source"]
        chunk_id = row["id"]

        # Score por keywords (sempre disponível)
        kw_score = _keyword_score(query, text)

        # Score por vetor (se disponível)
        vec_score = 0.0
        if query_embedding:
            try:
                stored_embedding = json.loads(row["embedding"])
                if stored_embedding:
                    vec_score = _cosine_similarity(query_embedding, stored_embedding)
            except (json.JSONDecodeError, TypeError):
                pass

        # Score combinado (híbrido)
        if query_embedding:
            final_score = (vector_weight * vec_score) + (keyword_weight * kw_score)
        else:
            # Sem embeddings: só keyword
            final_score = kw_score

        # Temporal decay (opcional): chunks mais recentes ganham leve boost
        age_days = (time.time() - (row["created_at"] or 0)) / 86400
        decay = 1.0 / (1.0 + age_days / 30)  # half-life de 30 dias
        final_score *= (0.9 + 0.1 * decay)

        if final_score >= min_score:
            scored.append((final_score, SearchResult(
                text=text,
                source=source,
                score=round(final_score, 4),
                chunk_id=chunk_id,
            )))

    # Ordena por score desc e retorna top N
    scored.sort(key=lambda x: x[0], reverse=True)
    return [sr for _, sr in scored[:max_results]]


def delete_by_source(source: str) -> int:
    """Remove todos os chunks de uma fonte."""
    init_vector_db()
    with _conn() as c:
        cur = c.execute("DELETE FROM chunks WHERE source=?", (source,))
    return cur.rowcount


def memory_stats() -> dict[str, Any]:
    """Estatísticas da memória vetorial."""
    init_vector_db()
    with _conn() as c:
        total = c.execute("SELECT COUNT(*) as n FROM chunks").fetchone()["n"]
        sources = c.execute("SELECT source, COUNT(*) as n FROM chunks GROUP BY source ORDER BY n DESC").fetchall()
        has_embeddings = c.execute("SELECT COUNT(*) as n FROM chunks WHERE embedding != '[]'").fetchone()["n"]

    return {
        "total_chunks": total,
        "chunks_with_embeddings": has_embeddings,
        "chunks_keyword_only": total - has_embeddings,
        "sources": {row["source"]: row["n"] for row in sources},
    }
