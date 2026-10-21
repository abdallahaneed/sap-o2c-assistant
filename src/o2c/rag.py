"""RAG over my own O2C process notes in knowledge/.

1. Split every note into chunks at its "## " headings.
2. Turn each chunk into a vector with a local multilingual model (no API cost, works in German).
3. Store the vectors in ChromaDB (data/chroma).
4. For a question, embed it the same way and return the closest chunks.

The index rebuilds itself when a note changes (we compare a hash of all chunk texts).
Run: uv run python -m o2c.rag "Was bedeutet Warenausgang?"
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import chromadb

from o2c.sap_client import PROJECT_ROOT

KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"
COLLECTION = "o2c_knowledge"
DEFAULT_MODEL = "intfloat/multilingual-e5-small"


@dataclass
class Chunk:
    id: str  # e.g. "02_sales_order.md#3"
    source: str  # file name
    heading: str
    text: str  # what gets embedded and returned


def split_note(path: Path) -> list[Chunk]:
    """One chunk per '## ' section. The note title goes into every chunk for context."""
    text = path.read_text(encoding="utf-8")
    # HTML comments hold writing prompts, they must not end up in the index
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    title_match = re.search(r"^# (.+)$", text, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path.stem
    parts = re.split(r"^## ", text, flags=re.MULTILINE)

    chunks = []
    # parts[0] is everything before the first "## ": the title and an optional intro
    intro = re.sub(r"^# .+$", "", parts[0], flags=re.MULTILINE).strip()
    sections = [(title, intro)] + [
        (p.split("\n", 1)[0].strip(), p.split("\n", 1)[1].strip() if "\n" in p else "")
        for p in parts[1:]
    ]
    for heading, body in sections:
        if not body:
            continue  # skip empty sections
        chunks.append(
            Chunk(
                id=f"{path.name}#{len(chunks)}",
                source=path.name,
                heading=heading,
                text=f"{title}: {heading}\n{body}" if heading != title else f"{title}\n{body}",
            )
        )
    return chunks


def load_chunks(folder: Path = KNOWLEDGE_DIR) -> list[Chunk]:
    return [c for path in sorted(folder.glob("*.md")) for c in split_note(path)]


def notes_hash(chunks: list[Chunk]) -> str:
    """Fingerprint of all chunk texts. Changes when any note changes."""
    joined = "\n\0".join(f"{c.id}\n{c.text}" for c in chunks)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


class Embedder(Protocol):
    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class E5Embedder:
    """e5 models expect a prefix: 'passage: ' for documents, 'query: ' for questions."""

    def __init__(self, model_name: str | None = None) -> None:
        # Import here: loading PyTorch takes a few seconds, only pay it when needed
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name or os.getenv("EMBED_MODEL", DEFAULT_MODEL))

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode([f"passage: {t}" for t in texts], normalize_embeddings=True)
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode([f"query: {text}"], normalize_embeddings=True)[0].tolist()


class KnowledgeBase:
    def __init__(
        self,
        client: Any | None = None,
        embedder: Embedder | None = None,
        folder: Path = KNOWLEDGE_DIR,
        collection: str = COLLECTION,
    ) -> None:
        self.client = client or chromadb.PersistentClient(path=str(CHROMA_DIR))
        self._embedder = embedder
        self.folder = folder
        self.collection_name = collection

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = E5Embedder()  # loaded on first use only
        return self._embedder

    def ensure_index(self) -> int:
        """Build the index if it is missing or the notes changed. Returns number of chunks."""
        chunks = load_chunks(self.folder)
        fingerprint = notes_hash(chunks)
        existing = {c.name for c in self.client.list_collections()}
        if self.collection_name in existing:
            col = self.client.get_collection(self.collection_name)
            if (col.metadata or {}).get("notes_hash") == fingerprint:
                return col.count()  # up to date, nothing to do
            self.client.delete_collection(self.collection_name)

        # cosine distance: compares direction of vectors, standard for text embeddings
        col = self.client.create_collection(
            self.collection_name, metadata={"hnsw:space": "cosine", "notes_hash": fingerprint}
        )
        if chunks:
            col.add(
                ids=[c.id for c in chunks],
                embeddings=self.embedder.embed_passages([c.text for c in chunks]),
                documents=[c.text for c in chunks],
                metadatas=[{"source": c.source, "heading": c.heading} for c in chunks],
            )
        return len(chunks)

    def search(self, query: str, k: int = 3) -> list[dict[str, Any]]:
        """Return the k closest chunks with source, heading, text and a similarity score."""
        if self.ensure_index() == 0:
            return []
        col = self.client.get_collection(self.collection_name)
        result = col.query(
            query_embeddings=[self.embedder.embed_query(query)],
            n_results=max(1, min(int(k), 10)),
        )
        return [
            {
                "source": meta["source"],
                "heading": meta["heading"],
                "text": doc,
                "score": round(1 - dist, 3),  # 1 = same meaning, 0 = unrelated
            }
            for doc, meta, dist in zip(
                result["documents"][0], result["metadatas"][0], result["distances"][0], strict=True
            )
        ]


_default_kb: KnowledgeBase | None = None


def search_process_knowledge(query: str, k: int = 3) -> list[dict[str, Any]]:
    """Tool for the assistant: find passages in my O2C notes that answer a process question."""
    global _default_kb
    if _default_kb is None:
        _default_kb = KnowledgeBase()  # one instance, so the model loads only once
    return _default_kb.search(query, k)


def main() -> None:
    query = " ".join(sys.argv[1:]) or "Was bedeutet Warenausgang?"
    print(f"Question: {query}\n")
    for hit in search_process_knowledge(query):
        print(f"[{hit['score']}] {hit['source']} > {hit['heading']}")
        print(f"  {hit['text'][:200].replace(chr(10), ' ')}\n")


if __name__ == "__main__":
    main()
