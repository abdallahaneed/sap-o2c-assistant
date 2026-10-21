"""Tests for RAG. A tiny fake embedder replaces the real model: fast, offline, predictable."""

import hashlib
import math
import re
import uuid

import chromadb
import pytest

from o2c.rag import KnowledgeBase, load_chunks, notes_hash, split_note


class WordHashEmbedder:
    """Bag of words: each word adds 1 to a slot chosen by its hash. Same words, close vectors."""

    dims = 256

    def _vec(self, text):
        vec = [0.0] * self.dims
        for word in re.findall(r"\w+", text.lower()):
            vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dims] += 1
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed_passages(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


NOTE_DELIVERY = """# Delivery and goods issue

Short intro about deliveries.

## Goods issue
Goods issue posts the stock movement. Stock goes down, cost of goods sold goes up.

## Empty section

## Picking
Picking takes the goods from the warehouse shelf.
"""

NOTE_BILLING = """# Billing

## Credit memo
A credit memo reduces revenue for the customer.
"""


@pytest.fixture
def notes(tmp_path):
    (tmp_path / "03_delivery.md").write_text(NOTE_DELIVERY)
    (tmp_path / "04_billing.md").write_text(NOTE_BILLING)
    return tmp_path


@pytest.fixture
def kb(notes):
    # Fresh collection name per test: Chroma's in-memory client is shared in one process
    return KnowledgeBase(
        client=chromadb.EphemeralClient(),
        embedder=WordHashEmbedder(),
        folder=notes,
        collection=f"test_{uuid.uuid4().hex[:8]}",
    )


def test_split_note_by_heading(notes):
    chunks = split_note(notes / "03_delivery.md")
    assert [c.heading for c in chunks] == ["Delivery and goods issue", "Goods issue", "Picking"]
    assert chunks[1].text.startswith("Delivery and goods issue: Goods issue")  # title as context


def test_load_chunks_reads_all_notes(notes):
    assert len(load_chunks(notes)) == 4


def test_search_finds_the_right_section(kb):
    hits = kb.search("what happens to stock at goods issue", k=1)
    assert (hits[0]["source"], hits[0]["heading"]) == ("03_delivery.md", "Goods issue")


def test_search_returns_score_between_0_and_1(kb):
    score = kb.search("credit memo revenue", k=1)[0]["score"]
    assert 0 < score <= 1


def test_index_rebuilds_when_a_note_changes(kb, notes):
    kb.ensure_index()
    (notes / "04_billing.md").write_text(
        NOTE_BILLING + "\n## Invoice\nAn invoice creates revenue.\n"
    )
    assert kb.ensure_index() == 5
    assert kb.search("invoice creates revenue", k=1)[0]["heading"] == "Invoice"


def test_hash_is_stable_for_same_notes(notes):
    assert notes_hash(load_chunks(notes)) == notes_hash(load_chunks(notes))


def test_empty_folder_returns_no_hits(tmp_path):
    kb = KnowledgeBase(
        client=chromadb.EphemeralClient(),
        embedder=WordHashEmbedder(),
        folder=tmp_path,
        collection=f"test_{uuid.uuid4().hex[:8]}",
    )
    assert kb.search("anything") == []


def test_comments_are_not_indexed(tmp_path):
    (tmp_path / "x.md").write_text("# T\n\n## Section\n<!-- prompt: explain this -->\n")
    assert split_note(tmp_path / "x.md") == []  # only a comment, so the section is empty
