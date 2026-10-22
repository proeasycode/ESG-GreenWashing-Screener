"""PDF processor: page-aware text & table extraction and environmental claim candidate detection.

Extraction strategy (graceful degradation):
1. PyMuPDF (fitz) - fast, robust text extraction with page numbers.
2. pdfplumber    - fallback text extractor and table extractor (tables are flattened to text rows).

The processor then splits pages into sentences and keeps "claim candidates": sentences that talk
about environmental performance (emissions, energy, water, waste, targets...). Each candidate keeps
its page number so every audited claim can be traced back to the source document.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

ENV_KEYWORDS = [
    "emission", "carbon", "co2", "ghg", "greenhouse", "climate", "net zero", "net-zero", "neutral",
    "renewable", "solar", "wind", "energy", "electricity", "scope 1", "scope 2", "scope 3",
    "water", "waste", "recycl", "circular", "pfc", "fluorinated", "sustainab", "eco-friendly",
    "green", "environment", "decarboni", "re100", "sbti", "science based", "offset", "biodiversity",
    "tco2e", "mwh", "gwh", "footprint", "planet", "clean", "plastic",
]
CLAIM_VERBS = [
    "reduc", "achiev", "commit", "target", "aim", "reach", "become", "cut", "lower", "increas",
    "improv", "transition", "aspire", "plan", "pledge", "deliver", "source", "procur", "install",
    "invest", "save", "avoid", "recycl", "lead", "strive", "power", "verified", "assured", "is ", "are ",
]
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])")
_WS = re.compile(r"\s+")


@dataclass
class PageText:
    page: int
    text: str
    tables: list[str] = field(default_factory=list)


@dataclass
class ClaimCandidate:
    page: int
    text: str
    relevance: float


@dataclass
class ParsedDocument:
    filename: str
    pages: list[PageText]
    engine: str

    @property
    def full_text(self) -> str:
        return "\n".join(p.text for p in self.pages)

    @property
    def n_pages(self) -> int:
        return len(self.pages)

    @property
    def n_words(self) -> int:
        return len(self.full_text.split())


def _extract_pymupdf(data: bytes) -> list[PageText]:
    import fitz  # PyMuPDF

    pages = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for i, page in enumerate(doc, 1):
            pages.append(PageText(i, page.get_text("text") or ""))
    return pages


def _extract_pdfplumber(data: bytes, with_tables: bool = True, max_table_pages: int = 60) -> list[PageText]:
    import pdfplumber

    pages = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            tables = []
            if with_tables and i <= max_table_pages:
                for table in page.extract_tables() or []:
                    rows = [" | ".join(str(c).strip() for c in row if c not in (None, "")) for row in table]
                    tables.extend(r for r in rows if r)
            pages.append(PageText(i, page.extract_text() or "", tables))
    return pages


def parse_pdf(data: bytes, filename: str = "report.pdf", extract_tables: bool = True) -> ParsedDocument:
    """Extract text page by page; tables are added with pdfplumber when available."""
    errors = []
    pages: list[PageText] = []
    engine = ""
    try:
        pages, engine = _extract_pymupdf(data), "PyMuPDF"
    except Exception as exc:  # noqa: BLE001 - any parser failure triggers the fallback
        errors.append(f"PyMuPDF: {exc}")
    if not pages or not any(p.text.strip() for p in pages):
        try:
            pages, engine = _extract_pdfplumber(data, with_tables=extract_tables), "pdfplumber"
        except Exception as exc:  # noqa: BLE001
            errors.append(f"pdfplumber: {exc}")
    elif extract_tables:
        try:
            plumber = _extract_pdfplumber(data, with_tables=True)
            for p, q in zip(pages, plumber):
                p.tables = q.tables
            engine += " + pdfplumber tables"
        except Exception:  # noqa: BLE001 - tables are optional
            pass
    if not pages:
        raise ValueError("Could not extract text from PDF. " + "; ".join(errors))
    return ParsedDocument(filename, pages, engine)


def split_sentences(text: str) -> list[str]:
    text = text.replace("\u00ad", "").replace("ﬁ", "fi").replace("ﬂ", "fl")
    text = re.sub(r"-\n(?=[a-z])", "", text)          # de-hyphenate line breaks
    text = _WS.sub(" ", text)
    return [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]


def claim_relevance(sentence: str) -> float:
    """Score how likely a sentence is an auditable environmental claim (0-1)."""
    low = sentence.lower()
    env = sum(1 for k in ENV_KEYWORDS if k in low)
    verb = any(v in low for v in CLAIM_VERBS)
    has_num = bool(re.search(r"\d", low))
    if env == 0 or not verb:
        return 0.0
    return round(min(1.0, 0.25 * env + (0.15 if has_num else 0) + 0.1), 2)


def extract_claim_candidates(doc: ParsedDocument, max_claims: int = 25, min_relevance: float = 0.35) -> list[ClaimCandidate]:
    """Return the most relevant, de-duplicated environmental claim sentences with page numbers."""
    seen: set[str] = set()
    cands: list[ClaimCandidate] = []
    for page in doc.pages:
        sentences = split_sentences(page.text) + [t for t in page.tables if len(t) > 30]
        for s in sentences:
            n_words = len(s.split())
            if n_words < 8 or n_words > 90:
                continue
            key = re.sub(r"[^a-z]", "", s.lower())[:120]
            if key in seen:
                continue
            rel = claim_relevance(s)
            if rel >= min_relevance:
                seen.add(key)
                cands.append(ClaimCandidate(page.page, s, rel))
    # keep the most relevant claims but present them in document order
    top = sorted(cands, key=lambda c: -c.relevance)[:max_claims]
    return sorted(top, key=lambda c: (c.page, cands.index(c)))


def guess_company_name(doc: ParsedDocument) -> str:
    """Best-effort company name from the first page (falls back to the file name)."""
    first = doc.pages[0].text if doc.pages else ""
    m = re.search(r"([A-Za-z0-9&\.\- ]{2,40}?)\s+(?:Sustainability|ESG|Corporate Social Responsibility|CSR|Impact|Climate|Environmental)\s+(?:Progress\s+)?Report", first, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        if len(name) >= 2 and not name.lower().startswith(("annual", "global", "corporate", "the")):
            return name.title()

    # Extract company name by cleaning report stopwords from filename
    fn = doc.filename.rsplit(".", 1)[0]
    fn_spaced = re.sub(r"[_\-]+", " ", fn)
    fn_clean = re.sub(r"\b(sustainability|environmental|progress|impact|climate|annual|report|esg|csr|sample|\d{4})\b", "", fn_spaced, flags=re.IGNORECASE)
    fn_clean = re.sub(r"\s+", " ", fn_clean).strip()
    if fn_clean and len(fn_clean) >= 2:
        return fn_clean.title()
    return fn_spaced.strip()[:40].title() or "Uploaded Company"
