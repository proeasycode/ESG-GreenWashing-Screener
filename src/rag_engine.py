"""RAG engine: chunking, vector indexing and retrieval of ESG reference standards.

The knowledge base (``data/knowledge_base``) is chunked by Markdown headings (one ``###`` section
= one chunk, tagged with its ``##`` standard family) plus one chunk per taxonomy pillar.

Vectorisation uses a TF-IDF embedding (word 1-2 grams, sublinear TF, L2-normalised), stored in an
in-memory dense vector store and searched by cosine similarity. This choice is deliberate for a
classroom-grade, production-safe demo: it is deterministic, needs no GPU, no API credits and no
network, and performs well on a small, terminology-dense regulatory corpus (exact codes such as
"GRI 305-3" or "TC-SC-110a.1" matter more than semantic paraphrase). The ``VectorStore`` interface
(add / search) is the single seam to swap in ChromaDB/FAISS with dense embeddings at scale.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "data" / "knowledge_base"
KB_MARKDOWN = KB_DIR / "esg_standards_kb.md"
KB_TAXONOMY = KB_DIR / "greenwashing_taxonomy.json"

# Short family tags used in the UI and in "matched standard" labels.
FAMILY_TAGS = {
    "GRI": "GRI", "SASB": "SASB", "TCFD": "TCFD", "ISSB": "ISSB",
    "CSRD": "CSRD / EU", "EU": "CSRD / EU", "Science": "SBTi / GHG Protocol", "Greenwashing": "Taxonomy",
}

# Domain synonyms injected at query time so that colloquial corporate wording hits regulatory text.
QUERY_EXPANSIONS = {
    r"net[- ]?zero|carbon neutral|climate neutral": "net-zero target base period interim milestones SBTi IFRS S2 targets offsets",
    r"renewable|solar|wind|re100|ppa|certificate": "renewable electricity market-based Scope 2 contractual instruments PPA REC GRI 305-2",
    r"supply chain|supplier|value chain|scope 3": "Scope 3 value chain categories GRI 305-3 purchased goods SBTi Scope 3 target",
    r"water|drought|recycl": "water withdrawal consumption water stress SASB TC-SC-140a.1 GRI 303",
    r"pfc|fluorinated|process gas|abatement": "perfluorinated compounds Scope 1 SASB TC-SC-110a.1 abatement",
    r"eco-friendly|green|sustainable|environmentally friendly": "generic environmental claims ban Directive 2024/825 substantiation",
    r"assur|verified|audit": "external assurance limited reasonable ISAE 3000 GRI 2-5",
    r"waste|circular|recycle": "hazardous waste recycled SASB TC-SC-150a.1 product end-of-life",
    r"intensity|per wafer|per unit|per revenue": "GHG emissions intensity ratio GRI 305-4 absolute emissions",
    r"offset|credit": "carbon credits offsets ISO 14068 neutrality ESRS E1-7",
}


@dataclass
class Chunk:
    chunk_id: str
    family: str
    title: str
    text: str
    source: str
    metadata: dict = field(default_factory=dict)

    @property
    def tag(self) -> str:
        for key, tag in FAMILY_TAGS.items():
            if self.family.startswith(key):
                return tag
        return self.family.split(":")[0]

    @property
    def label(self) -> str:
        """Short citation label, e.g. 'GRI 305-3 Other Indirect (Scope 3) GHG Emissions'."""
        return self.title


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float


def chunk_markdown(path: Path = KB_MARKDOWN) -> list[Chunk]:
    """Split the standards Markdown into heading-delimited chunks."""
    chunks: list[Chunk] = []
    family, title, buf = "", "", []

    def flush() -> None:
        body = " ".join(" ".join(buf).split())
        if title and body:
            cid = re.sub(r"[^a-z0-9]+", "-", f"{family}-{title}".lower()).strip("-")[:80]
            chunks.append(Chunk(cid, family, title, body, path.name))

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            flush()
            family, title, buf = line[3:].strip(), "", []
        elif line.startswith("### "):
            flush()
            title, buf = line[4:].strip(), []
        elif not line.startswith("# "):
            buf.append(line)
    flush()
    return chunks


def chunk_taxonomy(path: Path = KB_TAXONOMY) -> list[Chunk]:
    """One retrievable chunk per greenwashing pillar."""
    tax = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for key, p in tax["pillars"].items():
        text = (
            f"{p['name']} ({p['subtitle']}), weight {int(p['weight'] * 100)}%. {p['question']} "
            f"High risk: {p['high_risk_definition']} Legit: {p['legit_definition']} "
            f"Rubric: " + " ".join(f"[{k}] {v}" for k, v in p["rubric"].items())
            + f" Regulatory basis: {', '.join(p['regulatory_basis'])}."
        )
        out.append(Chunk(f"taxonomy-{key}", "Greenwashing Taxonomy", f"Pillar - {p['name']}", text, path.name, {"pillar": key}))
    return out


class VectorStore:
    """Minimal in-memory dense vector store with cosine similarity search."""

    def __init__(self) -> None:
        self.vectors: np.ndarray | None = None
        self.items: list[Chunk] = []

    def add(self, vectors: np.ndarray, items: list[Chunk]) -> None:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = vectors / np.where(norms == 0, 1, norms)
        self.vectors = vectors if self.vectors is None else np.vstack([self.vectors, vectors])
        self.items.extend(items)

    def search(self, query_vec: np.ndarray, k: int = 4, mask: np.ndarray | None = None) -> list[tuple[int, float]]:
        if self.vectors is None:
            return []
        q = query_vec / (np.linalg.norm(query_vec) or 1)
        sims = self.vectors @ q
        if mask is not None:
            sims = np.where(mask, sims, -1)
        top = np.argsort(-sims)[:k]
        return [(int(i), float(sims[i])) for i in top if sims[i] > 0]


class StandardsRetriever:
    """Index the ESG knowledge base and retrieve the regulatory standards relevant to a claim."""

    def __init__(self) -> None:
        self.chunks: list[Chunk] = chunk_markdown() + chunk_taxonomy()
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2), sublinear_tf=True, stop_words="english",
            token_pattern=r"(?u)\b[\w\-\.]*\w\b", min_df=1,
        )
        corpus = [f"{c.family} {c.title} {c.title} {c.text}" for c in self.chunks]
        matrix = self.vectorizer.fit_transform(corpus).toarray().astype(np.float32)
        self.store = VectorStore()
        self.store.add(matrix, self.chunks)

    @property
    def families(self) -> list[str]:
        return sorted({c.tag for c in self.chunks})

    @staticmethod
    def expand_query(query: str) -> str:
        extra = [exp for pat, exp in QUERY_EXPANSIONS.items() if re.search(pat, query, re.IGNORECASE)]
        return " ".join([query, *extra])

    def retrieve(self, query: str, k: int = 4, families: list[str] | None = None, expand: bool = True) -> list[RetrievedChunk]:
        q = self.expand_query(query) if expand else query
        vec = self.vectorizer.transform([q]).toarray()[0].astype(np.float32)
        mask = None
        if families:
            mask = np.array([c.tag in families for c in self.chunks])
        return [RetrievedChunk(self.chunks[i], round(s, 3)) for i, s in self.store.search(vec, k=k, mask=mask)]

    @staticmethod
    def format_context(results: list[RetrievedChunk], max_chars: int = 900) -> str:
        """Render retrieved chunks as a citation-friendly context block for the LLM prompt."""
        return "\n\n".join(
            f"[{i}] {r.chunk.family} > {r.chunk.title} (similarity {r.score:.2f})\n{r.chunk.text[:max_chars]}"
            for i, r in enumerate(results, 1)
        )

    @staticmethod
    def best_label(results: list[RetrievedChunk]) -> str:
        """Pick the most relevant non-taxonomy standard for the 'matched standard' column."""
        for r in results:
            if r.chunk.family != "Greenwashing Taxonomy":
                return f"{r.chunk.tag}: {r.chunk.title}"
        return results[0].chunk.title if results else "No standard retrieved"
