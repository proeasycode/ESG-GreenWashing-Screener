"""Scoring engine: deterministic computation of the Greenwashing Risk Index.

Two responsibilities:

1. ``HeuristicAnalyzer`` - an offline, rule-based NLP analyzer that scores a claim on the
   4 pillars using the lexicons stored in ``data/knowledge_base/greenwashing_taxonomy.json``.
   It is used (a) as the fallback when no LLM is available and (b) as the deterministic
   anchor of the hybrid LLM + rules score.

2. Pure scoring functions - claim risk, classification and company-level aggregation
   (Greenwashing Risk Index, legit ratio, pillar strengths, Talk-vs-Walk coordinates).

All pillar values are RISKS on a 0-100 scale (0 = fully substantiated, 100 = pure greenwashing).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
TAXONOMY_PATH = ROOT / "data" / "knowledge_base" / "greenwashing_taxonomy.json"

PILLARS: list[str] = ["quantification", "trajectory", "scope", "assurance"]
PILLAR_WEIGHTS: dict[str, float] = {
    "quantification": 0.30,
    "trajectory": 0.25,
    "scope": 0.25,
    "assurance": 0.20,
}
PILLAR_LABELS: dict[str, str] = {
    "quantification": "Quantification",
    "trajectory": "Roadmap",
    "scope": "Scope Coverage",
    "assurance": "Assurance",
}

# Hybrid blending: final pillar risk = ALPHA * LLM + (1 - ALPHA) * heuristic.
LLM_BLEND_ALPHA = 0.7
# Company index: GWRI = BETA * mean claim risk + (1 - BETA) * 100 * share of red-flag claims.
GWRI_BETA = 0.8

CLASS_META: dict[str, dict[str, str]] = {
    "legit": {"label": "Legit / Verified", "emoji": "🟢", "badge": "🟢 Legit", "color": "#22c55e"},
    "grey": {"label": "Grey Zone / Incomplete", "emoji": "🟡", "badge": "🟡 Grey Zone", "color": "#f59e0b"},
    "bullshit": {"label": "High Greenwashing Risk / Bullshit", "emoji": "🔴", "badge": "🔴 Bullshit", "color": "#ef4444"},
}


@lru_cache(maxsize=1)
def load_taxonomy() -> dict:
    """Load the 4-pillar taxonomy (cached)."""
    with open(TAXONOMY_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Pure scoring functions
# ---------------------------------------------------------------------------

def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def claim_risk(pillar_scores: dict[str, float]) -> float:
    """Weighted Greenwashing Risk of a single claim: R = sum_i w_i * r_i."""
    return round(sum(PILLAR_WEIGHTS[p] * clamp(pillar_scores.get(p, 50)) for p in PILLARS), 1)


def classify(risk: float) -> str:
    """Map a 0-100 risk to legit (0-48), grey (49-74) or bullshit (75-100)."""
    if risk <= 48:
        return "legit"
    if risk <= 74:
        return "grey"
    return "bullshit"


def blend_pillars(llm: dict[str, float] | None, heuristic: dict[str, float], alpha: float = LLM_BLEND_ALPHA) -> dict[str, float]:
    """Hybrid score: anchor the LLM judgement with deterministic rule-based evidence."""
    if not llm:
        return {p: round(clamp(heuristic[p]), 1) for p in PILLARS}
    return {p: round(clamp(alpha * clamp(llm.get(p, heuristic[p])) + (1 - alpha) * heuristic[p]), 1) for p in PILLARS}


def enrich_claim(claim: dict) -> dict:
    """Add risk_score, classification and badge to a claim dict that holds ``pillar_scores``."""
    risk = claim_risk(claim["pillar_scores"])
    cls = classify(risk)
    return {**claim, "risk_score": risk, "classification": cls, "badge": CLASS_META[cls]["badge"]}


def company_metrics(claims: list[dict], company: dict | None = None) -> dict:
    """Aggregate claim-level results into company-level KPIs.

    GWRI (Greenwashing Risk Index) = BETA * mean(R_c) + (1 - BETA) * 100 * red_share
    Walk score (verified proof)    = 0.4 * (100 - Q) + 0.3 * (100 - A) + 0.3 * Scope3 completeness
    Talk score (marketing volume)  = number of green marketing claims detected in the report
    """
    company = company or {}
    enriched = [c if "risk_score" in c else enrich_claim(c) for c in claims]
    n = len(enriched)
    if n == 0:
        return {
            "greenwashing_risk_index": 0.0, "total_claims": 0, "legit_claim_ratio": 0.0,
            "grey_claim_ratio": 0.0, "red_flag_ratio": 0.0, "mean_claim_risk": 0.0,
            "pillar_risk": {p: 0.0 for p in PILLARS}, "pillar_strength": {p: 100.0 for p in PILLARS},
            "walk_score": 0.0, "talk_score": 0, "claims": [],
        }
    risks = [c["risk_score"] for c in enriched]
    counts = {k: sum(1 for c in enriched if c["classification"] == k) for k in CLASS_META}
    pillar_risk = {p: round(mean(c["pillar_scores"][p] for c in enriched), 1) for p in PILLARS}
    red_share = counts["bullshit"] / n
    gwri = round(GWRI_BETA * mean(risks) + (1 - GWRI_BETA) * 100 * red_share, 1)
    scope3 = float(company.get("scope3_completeness", 100 - pillar_risk["scope"]))
    walk = round(0.4 * (100 - pillar_risk["quantification"]) + 0.3 * (100 - pillar_risk["assurance"]) + 0.3 * scope3, 1)
    return {
        "greenwashing_risk_index": gwri,
        "total_claims": n,
        "legit_claim_ratio": round(counts["legit"] / n, 3),
        "grey_claim_ratio": round(counts["grey"] / n, 3),
        "red_flag_ratio": round(red_share, 3),
        "mean_claim_risk": round(mean(risks), 1),
        "pillar_risk": pillar_risk,
        "pillar_strength": {p: round(100 - v, 1) for p, v in pillar_risk.items()},
        "walk_score": walk,
        "talk_score": int(company.get("marketing_claim_volume", n)),
        "claims": enriched,
    }


# ---------------------------------------------------------------------------
# Offline heuristic analyzer
# ---------------------------------------------------------------------------

_NUM = r"(?<![A-Za-z])\d{1,3}(?:[,\s]\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?"
_UNIT_RE = re.compile(
    rf"(?:{_NUM})\s*(?:%|percent\b|(?:million|billion|thousand)?\s*(?:metric\s+)?(?:t|kt|mt)?co2e?\b|"
    r"(?:million|billion|thousand)?\s*(?:metric\s+)?(?:tonnes|tons)\b|[kmgtp]wh\b|gj\b|tj\b|pj\b|m3\b|m³|"
    r"megalit(?:re|er)s?\b|cubic\s+met(?:re|er)s?\b|kg\b|(?:million|billion)\b)",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(19[89]\d|20[0-6]\d)\b")
_FY_RE = re.compile(r"\bfy\s?'?(\d{2,4})\b", re.IGNORECASE)


def _word_regex(terms: list[str]) -> re.Pattern:
    escaped = sorted((re.escape(t.strip()) for t in terms if t.strip()), key=len, reverse=True)
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(escaped) + r")(?![a-z0-9])", re.IGNORECASE)


@dataclass
class HeuristicResult:
    pillar_scores: dict[str, float]
    pillar_reasons: dict[str, str]
    signals: dict[str, list[str]] = field(default_factory=dict)


class HeuristicAnalyzer:
    """Rule-based NLP analyzer driven by the taxonomy lexicons (no API, deterministic)."""

    def __init__(self) -> None:
        tax = load_taxonomy()["pillars"]
        q, t, s, a = (tax[p]["lexicon"] for p in PILLARS)
        self.vague_re = _word_regex(q["vague_terms"])
        self.baseline_re = _word_regex(t["baseline_terms"])
        self.validation_re = _word_regex(t["validation_terms"])
        self.action_re = _word_regex(t["action_terms"])
        self.aspiration_re = _word_regex(t["aspiration_terms"])
        self.scope_res = {k: _word_regex(v) for k, v in s["scope_terms"].items()}
        self.material_re = _word_regex(s["material_sources"])
        self.marginal_re = _word_regex(s["marginal_initiatives"])
        self.assurer_re = _word_regex([x.strip() for x in a["assurers"]])
        self.assurance_re = _word_regex(a["assurance_terms"])
        self.standard_re = re.compile(r"(?<![a-z0-9])(?:" + "|".join(a["standard_patterns"]) + r")(?![a-z0-9])", re.IGNORECASE)
        self.target_re = re.compile(r"\b(net[- ]?zero|carbon[- ]neutral\w*|climate[- ]neutral\w*|re100|100% renewable|target|goal|by 20[2-6]\d|commit\w*)\b", re.IGNORECASE)

    @staticmethod
    def _found(pattern: re.Pattern, text: str) -> list[str]:
        return sorted({m.group(0).strip().lower() for m in pattern.finditer(text)})

    def analyze(self, text: str) -> HeuristicResult:
        low = f" {text.lower()} "
        sig: dict[str, list[str]] = {
            "metrics": self._found(_UNIT_RE, text),
            "vague_terms": self._found(self.vague_re, text),
            "years": sorted(set(_YEAR_RE.findall(text)) | {f"FY{y}" for y in _FY_RE.findall(text)}),
            "baseline": self._found(self.baseline_re, low),
            "validation": self._found(self.validation_re, low),
            "action_plan": self._found(self.action_re, low),
            "aspiration": self._found(self.aspiration_re, low),
            "scopes": [k for k, r in self.scope_res.items() if r.search(low)],
            "material_sources": self._found(self.material_re, low),
            "marginal": self._found(self.marginal_re, low),
            "assurers": self._found(self.assurer_re, low),
            "assurance": self._found(self.assurance_re, low),
            "standards": self._found(self.standard_re, text),
            "targets": self._found(self.target_re, text),
        }
        scores, reasons = {}, {}

        # Pillar 1 - Quantification (30%)
        n_m, n_v = len(sig["metrics"]), len(sig["vague_terms"])
        q = 60 - min(n_m, 3) * 18 + min(n_v, 4) * 9
        if n_m == 0 and not re.search(r"\d", text.replace("20", "", 1)):
            q += 20
        scores["quantification"] = clamp(q)
        reasons["quantification"] = (
            f"{n_m} hard metric(s) with units {sig['metrics'][:3]}" if n_m else "No figures with physical units"
        ) + (f"; vague buzzwords detected: {sig['vague_terms'][:4]}" if n_v else "; no vague buzzwords")

        # Pillar 2 - Trajectory & roadmap (25%)
        years = [int(y) for y in _YEAR_RE.findall(text)]
        future = [y for y in years if y >= 2026]
        long_term = any(y >= 2040 for y in future)
        interim = any(2026 <= y <= 2035 for y in future)
        past = any(y <= 2025 for y in years)
        forward = bool(future or sig["targets"] or sig["aspiration"])
        tr = 55.0
        if forward:
            tr += 15 if long_term and not interim else 0
            tr += 10 if sig["aspiration"] else 0
            tr -= 20 if (sig["baseline"] and past) else 0
            tr -= 12 if interim else 0
            tr -= 25 if sig["validation"] else 0
            tr -= 10 if sig["action_plan"] else 0
            if long_term and not interim and not sig["baseline"] and not sig["action_plan"]:
                tr = max(tr, 88)
        else:
            tr = 45 - (20 if (sig["baseline"] or len(years) >= 2) else 0) - (10 if n_m else 0)
        scores["trajectory"] = clamp(tr)
        parts = []
        parts.append("forward-looking target" if forward else "backward-looking performance statement")
        parts.append("baseline year present" if (sig["baseline"] and past) else "no baseline year")
        parts.append("interim milestone (2026-2035)" if interim else ("long-term only" if long_term else "no interim milestone"))
        if sig["validation"]:
            parts.append("SBTi / 1.5°C validation cited")
        if sig["action_plan"]:
            parts.append(f"action/CAPEX plan: {sig['action_plan'][:2]}")
        reasons["trajectory"] = "; ".join(parts)

        # Pillar 3 - Scope & materiality (25%)
        sc = 70 - 15 * len(sig["scopes"]) - (15 if "scope 3" in sig["scopes"] else 0)
        sc -= 10 if sig["material_sources"] else 0
        sc += 25 if sig["marginal"] and not sig["scopes"] else 0
        scores["scope"] = clamp(sc)
        reasons["scope"] = (
            (f"Covers {', '.join(s.title() for s in sig['scopes'])}" if sig["scopes"] else "No GHG scope boundary stated")
            + ("; Scope 3 value chain addressed" if "scope 3" in sig["scopes"] else "; Scope 3 omitted")
            + (f"; marginal initiative highlighted: {sig['marginal'][:3]}" if sig["marginal"] else "")
        )
        # TerraChoice "Sin of Irrelevance": a marginal initiative with no material scope
        # cannot earn credit for its metrics or roadmap, however precise they look.
        if sig["marginal"] and not sig["scopes"] and not sig["material_sources"]:
            scores["quantification"] = max(scores["quantification"], 70.0)
            scores["trajectory"] = max(scores["trajectory"], 70.0)
            reasons["quantification"] += "; figures describe a non-material initiative (sin of irrelevance)"
            reasons["trajectory"] += "; no roadmap for material emission sources"

        # Pillar 4 - Assurance & standard alignment (20%)
        base_a = 55.0 if n_m >= 1 else 75.0
        a = base_a - min(len(sig["standards"]), 2) * 15 - (25 if sig["assurers"] else 0) - (15 if sig["assurance"] else 0)
        scores["assurance"] = clamp(a)
        reasons["assurance"] = (
            (f"Standards referenced: {sig['standards'][:3]}" if sig["standards"] else "Standard indicator code implicit")
            + (f"; assurer: {sig['assurers'][:2]}" if sig["assurers"] else "")
            + (f"; {sig['assurance'][:2]}" if sig["assurance"] else "")
        )

        return HeuristicResult({p: round(v, 1) for p, v in scores.items()}, reasons, sig)

    def justification(self, result: HeuristicResult, standard: str = "") -> str:
        """Human-readable audit justification assembled from the rule signals."""
        risk = claim_risk(result.pillar_scores)
        cls = CLASS_META[classify(risk)]["label"]
        worst = max(PILLARS, key=lambda p: result.pillar_scores[p])
        ref = f" Cross-checked against {standard}." if standard else ""
        return (
            f"{cls} (risk {risk:.0f}/100). Weakest pillar: {PILLAR_LABELS[worst]} - "
            f"{result.pillar_reasons[worst]}.{ref}"
        )

    def buzzword_density(self, text: str) -> float:
        """Vague green buzzwords per 1,000 words (a 'talk' indicator for whole reports)."""
        words = max(1, len(text.split()))
        return round(1000 * len(self.vague_re.findall(text)) / words, 2)
