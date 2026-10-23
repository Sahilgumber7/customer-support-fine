"""BM25 retrieval over policy documents and help-centre articles.

Retrieved text is *data*. Nothing here can change authorisation, and the orchestrator
never executes instructions found inside a chunk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Plus

from .config import ROOT

_TOKEN = re.compile(r"[a-z0-9]+")

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "its",
    "just",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "please",
    "should",
    "so",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "to",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
}


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    title: str
    text: str
    version: str = ""
    score: float = 0.0


def _tokenize(text: str) -> list[str]:
    tokens = [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS and len(t) > 1]
    # Crude stemming so "refunds"/"refund" and "days"/"day" match.
    return [t[:-1] if len(t) > 4 and t.endswith("s") else t for t in tokens]


# Small, documented domain thesaurus applied to *queries only*. Customers say "send it
# back" and "reach my card"; the policy says "return" and "refund".
QUERY_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "back": ("return",),
    "card": ("refund",),
    "bank": ("refund",),
    "money": ("refund",),
    "parcel": ("shipment", "shipping"),
    "package": ("shipment", "shipping"),
    "late": ("delay", "shipping"),
    "broken": ("damaged", "return"),
    "faulty": ("defective", "warranty"),
    "guarantee": ("warranty",),
    "cancel": ("cancellation", "refund"),
    "size": ("sizing",),
}


def expand_query(query: str) -> list[str]:
    tokens = _tokenize(query)
    expanded = list(tokens)
    for token in tokens:
        expanded.extend(QUERY_EXPANSIONS.get(token, ()))
    return expanded


def _split_sections(doc_id: str, title: str, body: str, version: str) -> list[Chunk]:
    """Split on markdown headings so each chunk is a coherent policy clause."""
    chunks: list[Chunk] = []
    current_title = title
    buffer: list[str] = []
    for line in body.splitlines():
        if line.startswith("#"):
            if buffer:
                text = "\n".join(buffer).strip()
                if text:
                    chunks.append(Chunk(doc_id, current_title, text, version))
            current_title = f"{title} — {line.lstrip('# ').strip()}"
            buffer = []
        else:
            buffer.append(line)
    if buffer:
        text = "\n".join(buffer).strip()
        if text:
            chunks.append(Chunk(doc_id, current_title, text, version))
    return chunks


class Retriever:
    def __init__(self, chunks: list[Chunk]) -> None:
        self._chunks = chunks
        self._bm25 = (
            BM25Plus([_tokenize(c.title * 2 + " " + c.text) for c in chunks]) if chunks else None
        )

    @classmethod
    def from_directory(cls, path: Path | None = None) -> Retriever:
        path = path or (ROOT / "data" / "policy")
        chunks: list[Chunk] = []
        if path.exists():
            for file in sorted(path.glob("*.md")):
                body = file.read_text(encoding="utf-8")
                title = file.stem.replace("_", " ").title()
                version = ""
                for line in body.splitlines():
                    if line.lower().startswith("version:"):
                        version = line.split(":", 1)[1].strip()
                        break
                chunks.extend(_split_sections(file.stem, title, body, version))
        return cls(chunks)

    def add(self, chunk: Chunk) -> None:
        """Used by tests to inject adversarial documents."""
        self._chunks = [*self._chunks, chunk]
        self._bm25 = BM25Plus([_tokenize(c.title * 2 + " " + c.text) for c in self._chunks])

    def __len__(self) -> int:
        return len(self._chunks)

    @property
    def chunks(self) -> list[Chunk]:
        return list(self._chunks)

    def search(self, query: str, k: int = 4, min_score: float = 0.1) -> list[Chunk]:
        if not self._bm25 or not self._chunks:
            return []
        tokens = expand_query(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(zip(self._chunks, scores, strict=False), key=lambda pair: pair[1], reverse=True)
        return [
            Chunk(c.doc_id, c.title, c.text, c.version, round(float(s), 4))
            for c, s in ranked[:k]
            if s >= min_score
        ]

    def get(self, doc_id: str) -> Chunk | None:
        for chunk in self._chunks:
            if chunk.doc_id == doc_id:
                return chunk
        return None

