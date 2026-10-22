"""Agentic RAG screener: claim extraction, standards retrieval, LLM structured evaluation and scoring.

Agent loop for every batch of claim candidates mined from a report:

    1. PLAN      - offline heuristic pre-screen identifies the weakest pillars of each claim.
    2. RETRIEVE  - pillar-aware query rewriting + RAG retrieval of the relevant standards.
    3. EVALUATE  - LLM returns a Pydantic-validated structured audit (claim filter + 4 pillar risks).
    4. VERIFY    - hybrid reconciliation with the deterministic rule score; disagreements are logged.
    5. SCORE     - scoring_engine computes the weighted Greenwashing Risk and classification.

Providers: OpenAI, Google Gemini (Interactions API), NVIDIA NIM (OpenAI-compatible) or Mock Offline.
Any provider error (missing SDK, invalid key, quota, malformed JSON, network) degrades gracefully to
the offline heuristic analyzer, so a live presentation can never crash.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel, Field, ValidationError

from .pdf_processor import ClaimCandidate, ParsedDocument, extract_claim_candidates, guess_company_name
from .rag_engine import RetrievedChunk, StandardsRetriever
from .scoring_engine import (
    CLASS_META, PILLAR_LABELS, PILLARS, HeuristicAnalyzer, blend_pillars, claim_risk, classify,
    company_metrics, enrich_claim, load_taxonomy,
)

PROVIDERS = {
    "Mock Offline Fallback": {"env": None, "model_env": None, "default_model": "rule-based-heuristic-v1"},
    "Google Gemini": {"env": "GEMINI_API_KEY", "model_env": "GEMINI_MODEL", "default_model": "gemini-3.8-flash"},
    "OpenAI": {"env": "OPENAI_API_KEY", "model_env": "OPENAI_MODEL", "default_model": "gpt-4o-mini"},
    "NVIDIA NIM": {"env": "NVIDIA_API_KEY", "model_env": "NVIDIA_MODEL", "default_model": "meta/llama-3.3-70b-instruct"},
}
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

CATEGORY_RULES = [
    ("Net-Zero & Targets", r"net[- ]?zero|carbon neutral|climate neutral|target|by 20[3-6]\d|sbti|re100"),
    ("Supply Chain (Scope 3)", r"scope 3|supplier|supply chain|value chain|purchased goods|category 1"),
    ("Renewable Energy", r"renewable|solar|wind|ppa|green electricity|re100|certificate"),
    ("GHG Emissions", r"scope 1|scope 2|emission|tco2|ghg|pfc|fluorinated|carbon"),
    ("Water Stewardship", r"water|wastewater|drought|upw"),
    ("Waste & Circularity", r"waste|recycl|circular|landfill|plastic|packaging"),
    ("Energy Efficiency", r"energy efficien|energy saving|mwh|gwh|power consumption|performance per watt"),
]


def categorize(text: str) -> str:
    for name, pat in CATEGORY_RULES:
        if re.search(pat, text, re.IGNORECASE):
            return name
    return "General Green Marketing"


# ---------------------------------------------------------------------------
# Pydantic structured-output schema
# ---------------------------------------------------------------------------

class PillarAssessment(BaseModel):
    risk: int = Field(ge=0, le=100, description="Greenwashing risk for this pillar: 0 = fully substantiated, 100 = pure greenwashing.")
    rationale: str = Field(description="One-sentence evidence-based rationale citing what is present or missing.")


class ClaimAudit(BaseModel):
    claim_id: str = Field(description="Identifier of the claim exactly as given in the input (e.g. C03).")
    is_environmental_claim: bool = Field(description="False if the sentence is not an auditable environmental claim.")
    normalized_claim: str = Field(description="The claim rewritten as one clean, self-contained sentence.")
    quantification: PillarAssessment
    trajectory: PillarAssessment
    scope: PillarAssessment
    assurance: PillarAssessment
    matched_standard: str = Field(description="Most relevant standard requirement from the retrieved context, e.g. 'GRI 305-3' or 'IFRS S2 para 33-36'.")
    audit_justification: str = Field(description="2-3 sentence auditor verdict explaining the classification.")


class BatchAudit(BaseModel):
    audits: list[ClaimAudit]


def inline_schema(model: type[BaseModel]) -> dict:
    """Return a JSON schema with all $ref resolved (portable across providers)."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(defs[node["$ref"].split("/")[-1]])
            return {k: resolve(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [resolve(x) for x in node]
        return node

    return resolve(schema)


BATCH_SCHEMA = inline_schema(BatchAudit)


def _system_prompt() -> str:
    tax = load_taxonomy()
    rubric = []
    for key in PILLARS:
        p = tax["pillars"][key]
        rubric.append(
            f"- {key} ({p['name']}, weight {int(p['weight'] * 100)}%): {p['question']} "
            f"HIGH RISK = {p['high_risk_definition']} LEGIT = {p['legit_definition']} "
            + " ".join(f"[{k}] {v}" for k, v in p["rubric"].items())
        )
    return (
        "You are a senior ESG assurance auditor and greenwashing investigator. You cross-examine corporate "
        "environmental claims against international standards (GRI, SASB, TCFD, ISSB IFRS S1/S2, EU CSRD/ESRS, "
        "EU Directive 2024/825, SBTi). Be skeptical, evidence-based and consistent. Judge ONLY what the claim "
        "text itself discloses; never assume missing evidence exists elsewhere.\n\n"
        "Score each pillar as a RISK from 0 (fully substantiated) to 100 (pure greenwashing):\n"
        + "\n".join(rubric)
        + "\n\nUse the numbered REGULATORY CONTEXT passages to justify verdicts and fill matched_standard with the "
        "most specific requirement. Return ONLY a JSON object matching this JSON schema:\n"
        + json.dumps(BATCH_SCHEMA)
    )


# ---------------------------------------------------------------------------
# Multi-provider LLM client
# ---------------------------------------------------------------------------

class LLMError(RuntimeError):
    pass


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


class LLMClient:
    """Thin wrapper returning parsed JSON from OpenAI, Gemini or NVIDIA NIM."""

    def __init__(self, provider: str, api_key: str = "", model: str = "") -> None:
        self.provider = provider
        cfg = PROVIDERS.get(provider, PROVIDERS["Mock Offline Fallback"])
        self.api_key = (api_key or (os.getenv(cfg["env"], "") if cfg["env"] else "")).strip()
        self.model = model or (os.getenv(cfg["model_env"], "") if cfg["model_env"] else "") or cfg["default_model"]

    @property
    def available(self) -> bool:
        return self.provider != "Mock Offline Fallback" and bool(self.api_key)

    def complete_json(self, system: str, user: str) -> dict:
        if not self.available:
            raise LLMError("No LLM configured")
        try:
            if self.provider == "Google Gemini":
                return self._gemini(system, user)
            return self._openai_compatible(system, user)
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalise every SDK / network error
            raise LLMError(f"{self.provider} call failed: {type(exc).__name__}: {str(exc)[:300]}") from exc

    def _gemini(self, system: str, user: str) -> dict:
        try:
            from google import genai
        except ImportError as exc:
            raise LLMError("google-genai SDK not installed (pip install google-genai)") from exc
        client = genai.Client(api_key=self.api_key)
        interaction = client.interactions.create(
            model=self.model,
            system_instruction=system,
            input=user,
            response_format={"type": "text", "mime_type": "application/json", "schema": BATCH_SCHEMA},
            store=False,
        )
        return _extract_json(interaction.output_text)

    def _openai_compatible(self, system: str, user: str) -> dict:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMError("openai SDK not installed (pip install openai)") from exc
        base_url = NVIDIA_BASE_URL if self.provider == "NVIDIA NIM" else None
        client = OpenAI(api_key=self.api_key, base_url=base_url, timeout=90)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            resp = client.chat.completions.create(
                model=self.model, messages=messages, temperature=0.1,
                response_format={"type": "json_object"}, max_tokens=4096,
            )
        except Exception:  # noqa: BLE001 - some NIM models reject response_format: retry plain
            resp = client.chat.completions.create(model=self.model, messages=messages, temperature=0.1, max_tokens=4096)
        return _extract_json(resp.choices[0].message.content)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

@dataclass
class AgentTrace:
    steps: list[dict] = field(default_factory=list)

    def log(self, stage: str, message: str, **data) -> None:
        self.steps.append({"t": time.strftime("%H:%M:%S"), "stage": stage, "message": message, **data})


PILLAR_QUERY_HINTS = {
    "quantification": "quantified metrics units tCO2e MWh generic environmental claims substantiation",
    "trajectory": "target base period interim milestones SBTi transition plan IFRS S2 targets",
    "scope": "Scope 1 Scope 2 Scope 3 value chain materiality SASB",
    "assurance": "external assurance limited reasonable ISAE 3000 GRI 2-5 standard indicator",
}


class GreenwashAgent:
    """Agentic RAG auditor combining retrieval, an optional LLM and deterministic scoring."""

    def __init__(self, provider: str = "Mock Offline Fallback", api_key: str = "", model: str = "",
                 retriever: StandardsRetriever | None = None, top_k: int = 4, batch_size: int = 6) -> None:
        self.llm = LLMClient(provider, api_key, model)
        self.retriever = retriever or StandardsRetriever()
        self.heuristic = HeuristicAnalyzer()
        self.top_k = top_k
        self.batch_size = batch_size
        self.llm_failed_reason: str | None = None

    @property
    def engine_label(self) -> str:
        if self.llm.available and not self.llm_failed_reason:
            return f"Hybrid: {self.llm.provider} ({self.llm.model}) x rules"
        return "Offline heuristic analyzer (rule-based NLP)"

    # -- step 1 + 2: plan & retrieve --------------------------------------
    def plan_and_retrieve(self, text: str) -> tuple:
        h = self.heuristic.analyze(text)
        weak = sorted(PILLARS, key=lambda p: -h.pillar_scores[p])[:2]
        query = f"{text} {' '.join(PILLAR_QUERY_HINTS[p] for p in weak)}"
        retrieved = self.retriever.retrieve(query, k=self.top_k)
        return h, weak, retrieved

    # -- step 3: evaluate with LLM -----------------------------------------
    def _llm_batch(self, batch: list[dict], trace: AgentTrace) -> dict[str, ClaimAudit]:
        blocks = []
        for item in batch:
            blocks.append(
                f"### CLAIM {item['claim_id']} (page {item['page']})\n\"{item['text']}\"\n"
                f"REGULATORY CONTEXT for {item['claim_id']}:\n{StandardsRetriever.format_context(item['retrieved'], 600)}"
            )
        user = (
            "Audit each claim below. Return one entry in 'audits' per claim_id.\n\n" + "\n\n".join(blocks)
        )
        started = time.time()
        raw = self.llm.complete_json(_system_prompt(), user)
        try:
            parsed = BatchAudit.model_validate(raw)
        except ValidationError:
            # tolerate a bare list or a single object
            if isinstance(raw, list):
                parsed = BatchAudit(audits=[ClaimAudit.model_validate(x) for x in raw])
            elif isinstance(raw, dict) and "claim_id" in raw:
                parsed = BatchAudit(audits=[ClaimAudit.model_validate(raw)])
            else:
                raise
        trace.log("EVALUATE", f"{self.llm.provider} returned {len(parsed.audits)} validated audits in {time.time() - started:.1f}s")
        return {a.claim_id: a for a in parsed.audits}

    # -- steps 4 + 5: verify & score ---------------------------------------
    def _assemble(self, item: dict, audit: ClaimAudit | None, trace: AgentTrace) -> dict | None:
        h = item["heuristic"]
        retrieved: list[RetrievedChunk] = item["retrieved"]
        if audit is not None and not audit.is_environmental_claim:
            trace.log("FILTER", f"{item['claim_id']} discarded by LLM (not an environmental claim)")
            return None
        if audit is not None:
            llm_scores = {p: getattr(audit, p).risk for p in PILLARS}
            pillars = blend_pillars(llm_scores, h.pillar_scores)
            gaps = {p: abs(llm_scores[p] - h.pillar_scores[p]) for p in PILLARS}
            big = [PILLAR_LABELS[p] for p, g in gaps.items() if g >= 40]
            if big:
                trace.log("VERIFY", f"{item['claim_id']}: LLM vs rules disagreement on {', '.join(big)} - reconciled by hybrid blend")
            rationales = {p: getattr(audit, p).rationale for p in PILLARS}
            justification = audit.audit_justification
            matched = audit.matched_standard or StandardsRetriever.best_label(retrieved)
            text = audit.normalized_claim or item["text"]
            engine = f"{self.llm.provider} + rules"
        else:
            pillars = blend_pillars(None, h.pillar_scores)
            rationales = h.pillar_reasons
            matched = StandardsRetriever.best_label(retrieved)
            justification = self.heuristic.justification(h, matched)
            text = item["text"]
            engine = "Heuristic"
        claim = enrich_claim({
            "claim_id": item["claim_id"],
            "page": item["page"],
            "claim_text": text,
            "claim_category": categorize(text),
            "pillar_scores": pillars,
            "pillar_rationales": rationales,
            "matched_standard": matched,
            "retrieved_standards": [f"{r.chunk.tag}: {r.chunk.title} ({r.score:.2f})" for r in retrieved],
            "audit_justification": justification,
            "engine": engine,
        })
        trace.log("SCORE", f"{item['claim_id']} -> risk {claim['risk_score']:.0f} {CLASS_META[claim['classification']]['emoji']}")
        return claim

    def audit_claims(self, candidates: list[ClaimCandidate], progress: Callable[[float, str], None] | None = None) -> tuple[list[dict], AgentTrace]:
        trace = AgentTrace()
        trace.log("PLAN", f"{len(candidates)} claim candidates queued; engine = {self.engine_label}")
        items = []
        for i, c in enumerate(candidates, 1):
            h, weak, retrieved = self.plan_and_retrieve(c.text)
            items.append({"claim_id": f"C{i:02d}", "page": c.page, "text": c.text, "heuristic": h, "retrieved": retrieved})
            trace.log("RETRIEVE", f"C{i:02d} (p.{c.page}) weak pillars {[PILLAR_LABELS[p] for p in weak]} -> {StandardsRetriever.best_label(retrieved)}")
        claims: list[dict] = []
        n_batches = max(1, -(-len(items) // self.batch_size))
        for b in range(n_batches):
            batch = items[b * self.batch_size:(b + 1) * self.batch_size]
            if progress:
                progress(b / n_batches, f"Auditing batch {b + 1}/{n_batches} ({len(batch)} claims)")
            audits: dict[str, ClaimAudit] = {}
            if self.llm.available and not self.llm_failed_reason:
                try:
                    audits = self._llm_batch(batch, trace)
                except Exception as exc:  # noqa: BLE001 - graceful degradation is a hard requirement
                    self.llm_failed_reason = str(exc)[:300]
                    trace.log("FALLBACK", f"LLM unavailable ({self.llm_failed_reason}); switching to offline heuristic analyzer")
            for item in batch:
                claim = self._assemble(item, audits.get(item["claim_id"]), trace)
                if claim:
                    claims.append(claim)
        if progress:
            progress(1.0, "Audit complete")
        return claims, trace

    def audit_document(self, doc: ParsedDocument, company_name: str = "", sector: str = "", max_claims: int = 20,
                       progress: Callable[[float, str], None] | None = None) -> dict:
        """Full pipeline for one uploaded PDF -> company record compatible with the benchmark dataset."""
        candidates = extract_claim_candidates(doc, max_claims=max_claims)
        claims, trace = self.audit_claims(candidates, progress)
        
        # Auto-detect company name and sector via LLM / rules if not provided
        detected_name, detected_sector = self.identify_company_and_sector(doc)
        name = company_name.strip() if company_name.strip() else detected_name
        final_sector = sector.strip() if (sector.strip() and sector.lower() not in ("auto", "uploaded report", "")) else detected_sector
        trace.log("METADATA", f"Audited Entity: '{name}' | Identified Sector: '{final_sector}'")

        full = doc.full_text
        vague_sentences = sum(1 for p in doc.pages for s in re.split(r"(?<=[.!?])\s+", p.text) if self.heuristic.vague_re.search(s))
        scope3_hits = len(re.findall(r"scope\s*3", full, re.IGNORECASE))
        scope3_cat = len(set(re.findall(r"category\s*(\d{1,2})", full, re.IGNORECASE)))
        company = {
            "company": name,
            "ticker": "UPLOAD",
            "country": "-",
            "sector": final_sector or "Technology & General Industry",
            "report_title": doc.filename,
            "report_year": "-",
            "pages": doc.n_pages,
            "assurance_provider": self._detect_assurer(full),
            "assurance_level": self._detect_assurance_level(full),
            "scope3_completeness": min(100, 15 * min(scope3_hits, 3) + 4 * scope3_cat),
            "marketing_claim_volume": vague_sentences,
            "green_buzzword_density": self.heuristic.buzzword_density(full),
            "standard_alignment": self._standard_alignment(full),
            "source": "live",
        }
        metrics = company_metrics(claims, company)
        return {**company, **metrics, "trace": trace.steps, "engine": self.engine_label,
                "parser": doc.engine, "llm_warning": self.llm_failed_reason, "n_candidates": len(candidates),
                "auto_detected": {"company": detected_name, "sector": detected_sector}}

    def audit_text(self, text: str) -> dict:
        """Live RAG Query Tester: dissect and score a single sentence."""
        claims, trace = self.audit_claims([ClaimCandidate(page=0, text=text.strip(), relevance=1.0)])
        h = self.heuristic.analyze(text)
        if not claims:  # LLM judged it non-environmental: still show the rule-based dissection
            claims = [self._assemble({"claim_id": "C01", "page": 0, "text": text, "heuristic": h,
                                      "retrieved": self.retriever.retrieve(text, k=self.top_k)}, None, trace)]
        return {"claim": claims[0], "signals": h.signals, "trace": trace.steps,
                "retrieved": self.retriever.retrieve(text, k=self.top_k),
                "engine": self.engine_label, "llm_warning": self.llm_failed_reason}

    # -- document-level detectors & auto-identification ---------------------
    def identify_company_and_sector(self, doc: ParsedDocument) -> tuple[str, str]:
        """Automatically identify company name and industry sector using LLM or rule-based heuristics."""
        rule_name = guess_company_name(doc)
        rule_sector = self._detect_sector_heuristic(doc)

        if self.llm.available and not self.llm_failed_reason:
            try:
                preview = " \n ".join(p.text for p in doc.pages[:3])[:2500]
                prompt = (
                    "You are an expert corporate sustainability auditor and ESG taxonomist.\n"
                    "Analyze the following document excerpt (cover and executive pages of a corporate sustainability report):\n"
                    "1. Extract the official Company Name (e.g. 'Apple Inc.', 'Tesla, Inc.', 'TotalEnergies').\n"
                    "2. Determine the primary Industry Sector according to standard SASB/GRI classification, choosing a clean concise label such as:\n"
                    "   'Consumer Hardware & Tech', 'Semiconductors & Electronics', 'Automotive & Mobility', 'Energy & Utilities', "
                    "'Software & Cloud Services', 'Retail & Consumer Goods', 'Finance & Banking', 'Healthcare & Pharma', "
                    "'Aerospace & Heavy Industry', or similar standard industry label.\n\n"
                    f"Filename: {doc.filename}\n"
                    f"Report Excerpt:\n{preview}\n\n"
                    "Respond with a strict JSON object with exactly two keys: 'company_name' and 'sector'."
                )
                if self.llm.provider == "Google Gemini":
                    from google import genai
                    client = genai.Client(api_key=self.llm.api_key)
                    resp = client.models.generate_content(
                        model=self.llm.model,
                        contents=prompt,
                        config={"response_mime_type": "application/json"}
                    )
                    res_json = _extract_json(resp.text)
                else:
                    res_json = self.llm.complete_json(
                        system="You are an expert corporate sustainability and ESG industry taxonomy auditor.",
                        user=prompt,
                    )
                name = str(res_json.get("company_name", "")).strip() or rule_name
                sec = str(res_json.get("sector", "")).strip() or rule_sector
                return name, sec
            except Exception:
                pass

        return rule_name, rule_sector

    def _detect_sector_heuristic(self, doc: ParsedDocument) -> str:
        """Rule-based industry sector classifier based on keyword frequencies in early pages."""
        text = " \n ".join(p.text.lower() for p in doc.pages[:5])
        filename = doc.filename.lower()
        full = f"{filename} {text}"

        # Direct brand / corporate profile triggers
        if "apple" in full:
            return "Consumer Hardware & Tech"
        if "tsmc" in full or "taiwan semiconductor" in full:
            return "Semiconductors & Electronics"
        if "nvidia" in full:
            return "Fabless Semiconductors / AI Computing"
        if "intel" in full:
            return "Semiconductors & Electronics"
        if "tesla" in full:
            return "Automotive & Mobility"
        if any(oil in full for oil in ("totalenergies", "shell", "bp ", "exxon", "chevron", "petroleum")):
            return "Energy & Utilities"

        scores = {
            "Semiconductors & Electronics": len(re.findall(r"\b(wafer|fab|foundry|semiconductor|chips|microelectronics|integrated circuit|packaging|osat)\b", full)),
            "Consumer Hardware & Tech": len(re.findall(r"\b(iphone|macbook|ipad|smartphone|laptop|devices|consumer electronics|hardware products)\b", full)),
            "Automotive & Mobility": len(re.findall(r"\b(automotive|vehicles|car|ev|electric vehicle|powertrain|oem|passenger car|fleet)\b", full)),
            "Energy & Utilities": len(re.findall(r"\b(oil|gas|petroleum|utility|utilities|grid|power generation|refinery|megawatt|drilling)\b", full)),
            "Software & Cloud Services": len(re.findall(r"\b(software|cloud|datacenter|saas|hyperscale|ai platform|server)\b", full)),
            "Finance & Banking": len(re.findall(r"\b(banking|bank|asset management|investment|portfolio|financed emissions|lending)\b", full)),
            "Retail & Consumer Goods": len(re.findall(r"\b(apparel|clothing|fashion|footwear|beverage|food|supermarket|retailer)\b", full)),
            "Healthcare & Pharma": len(re.findall(r"\b(pharmaceutical|pharma|biotech|drug|therapeutics|clinical|patient|hospital)\b", full)),
            "Aerospace & Heavy Industry": len(re.findall(r"\b(aircraft|aviation|airline|aerospace|steel|cement|mining|chemicals)\b", full)),
        }
        best_sec, best_score = max(scores.items(), key=lambda item: item[1])
        if best_score >= 2:
            return best_sec
        return "Technology & General Industry"

    def _detect_assurer(self, text: str) -> str:
        found = self.heuristic._found(self.heuristic.assurer_re, f" {text.lower()} ")
        return ", ".join(x.upper() if len(x) <= 4 else x.title() for x in found[:2]) or "None detected"

    @staticmethod
    def _detect_assurance_level(text: str) -> str:
        low = text.lower()
        if "reasonable assurance" in low:
            return "Reasonable"
        if "limited assurance" in low:
            return "Limited"
        return "None"

    @staticmethod
    def _standard_alignment(text: str) -> dict[str, float]:
        """Crude coverage proxy: density of standard-specific codes and keywords (0-100)."""
        low = text.lower()
        patterns = {
            "GRI": [r"gri\s?\d{3}", r"gri content index", r"gri 2-5"],
            "SASB": [r"sasb", r"tc-[a-z]{2}-\d{3}a"],
            "TCFD": [r"tcfd", r"scenario analysis", r"physical risk", r"transition risk"],
            "ISSB": [r"issb", r"ifrs s[12]"],
            "CSRD": [r"csrd", r"esrs", r"double materiality"],
        }
        out = {}
        for std, pats in patterns.items():
            hits = sum(len(re.findall(p, low)) for p in pats)
            out[std] = float(min(100, round(25 * (hits ** 0.5))))
        return out


def quick_score(pillars: dict[str, float]) -> tuple[float, str]:
    """Convenience helper for the UI."""
    r = claim_risk(pillars)
    return r, classify(r)
