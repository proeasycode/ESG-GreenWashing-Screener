"""FastAPI Backend Server for GreenWash-Screener.

Provides RESTful endpoints for:
- Pre-loaded benchmark companies & claims (/api/benchmark)
- Single company audit & claims details (/api/companies/{name})
- Real-time RAG single-claim tester (/api/audit/claim)
- Live PDF sustainability report audit (/api/audit/pdf)
- RAG standards corpus & taxonomy (/api/standards, /api/taxonomy)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.agent_screener import (
    GreenwashAgent,
    PROVIDERS,
)
from src.pdf_processor import parse_pdf
from src.rag_engine import StandardsRetriever
from src.scoring_engine import (
    CLASS_META,
    PILLAR_LABELS,
    PILLARS,
    HeuristicAnalyzer,
    company_metrics,
    enrich_claim,
    load_taxonomy,
)

# Initialize app
app = FastAPI(
    title="GreenWash-Screener API",
    description="Agentic RAG for Corporate Sustainability Auditing & Multi-Standard ESG Verification",
    version="1.0.0",
)

# Enable CORS for local or remote frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singletons
retriever = StandardsRetriever()
heuristic = HeuristicAnalyzer()
taxonomy_data = load_taxonomy()

CUSTOM_COMPANIES_PATH = ROOT / "data" / "sample_reports" / "custom_companies.json"

def load_custom_companies() -> list[dict]:
    if not CUSTOM_COMPANIES_PATH.exists():
        return []
    try:
        with open(CUSTOM_COMPANIES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_custom_company_record(company_data: dict) -> dict:
    """Save or update a company record in the custom companies database."""
    customs = load_custom_companies()
    comp_name = company_data.get("company", "Uploaded Company").strip()
    
    # Enrich and recalculate metrics if claims present
    claims = company_data.get("claims", [])
    if claims:
        company_data.update(company_metrics(claims, company_data))
    
    company_data["is_custom"] = True
    company_data["sector"] = company_data.get("sector") or "Other / Custom"
    
    # Replace existing or append
    existing_idx = next((i for i, c in enumerate(customs) if c.get("company", "").lower() == comp_name.lower()), None)
    if existing_idx is not None:
        customs[existing_idx] = company_data
    else:
        customs.append(company_data)
        
    CUSTOM_COMPANIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CUSTOM_COMPANIES_PATH, "w", encoding="utf-8") as f:
        json.dump(customs, f, indent=2, ensure_ascii=False)
        
    global benchmark_cache
    benchmark_cache = get_benchmark_data()
    return company_data

def delete_custom_company_record(company_name: str) -> bool:
    customs = load_custom_companies()
    new_customs = [c for c in customs if c.get("company", "").lower() != company_name.lower()]
    if len(new_customs) != len(customs):
        with open(CUSTOM_COMPANIES_PATH, "w", encoding="utf-8") as f:
            json.dump(new_customs, f, indent=2, ensure_ascii=False)
        global benchmark_cache
        benchmark_cache = get_benchmark_data()
        return True
    return False

# Cache benchmark data
def get_benchmark_data() -> dict:
    benchmark_path = ROOT / "data" / "sample_reports" / "semiconductor_esg_benchmark.json"
    with open(benchmark_path, encoding="utf-8") as f:
        data = json.load(f)
        
    for comp in data["companies"]:
        comp["is_custom"] = False
        comp.update(company_metrics(comp["claims"], comp))
        
    # Merge custom saved companies
    custom_comps = load_custom_companies()
    base_names = {c["company"].lower() for c in data["companies"]}
    for cc in custom_comps:
        cc["is_custom"] = True
        if "claims" in cc:
            cc.update(company_metrics(cc["claims"], cc))
        if cc["company"].lower() in base_names:
            # Overwrite base if user saved custom version
            data["companies"] = [c if c["company"].lower() != cc["company"].lower() else cc for c in data["companies"]]
        else:
            data["companies"].append(cc)
            
    # Extract unique sectors
    sectors = sorted(list({c.get("sector", "Other") for c in data["companies"] if c.get("sector")}))
    data["sectors"] = sectors
    return data

benchmark_cache = get_benchmark_data()


# ---------------------------------------------------------------------------
# Pydantic Request & Response Models
# ---------------------------------------------------------------------------
class AuditTextRequest(BaseModel):
    text: str
    provider: Optional[str] = "Mock Offline Fallback"
    api_key: Optional[str] = ""
    model: Optional[str] = ""

class PillarScores(BaseModel):
    quantification: float
    trajectory: float
    scope: float
    assurance: float


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "GreenWash-Screener API", "version": "1.0.0"}


@app.get("/api/providers")
def get_providers():
    """List available LLM providers and their configuration."""
    return {
        "providers": list(PROVIDERS.keys()),
        "configs": {
            k: {
                "default_model": v["default_model"],
                "has_env_key": bool(os.getenv(v["env"])) if v.get("env") else False,
            }
            for k, v in PROVIDERS.items()
        },
    }


@app.get("/api/benchmark")
def get_benchmark(sector: Optional[str] = None):
    """Get all benchmark companies with calculated metrics and sector filtering."""
    data = benchmark_cache
    if sector and sector.lower() != "all":
        filtered = [c for c in data["companies"] if c.get("sector", "").lower() == sector.lower()]
        return {**data, "companies": filtered}
    return data


@app.get("/api/benchmark/companies/{company_name}")
def get_company_detail(company_name: str):
    """Get single company details from benchmark."""
    for c in benchmark_cache["companies"]:
        if c["company"].lower() == company_name.lower():
            return c
    raise HTTPException(status_code=404, detail=f"Company '{company_name}' not found")


@app.post("/api/benchmark/save")
def save_company_to_benchmark(company: dict):
    """Save an audited company into the persistent benchmark dataset."""
    if not company.get("company"):
        raise HTTPException(status_code=400, detail="Company name is required")
    saved = save_custom_company_record(company)
    return {"status": "ok", "saved_company": saved["company"], "sector": saved.get("sector")}


@app.delete("/api/benchmark/companies/{company_name}")
def delete_company_from_benchmark(company_name: str):
    """Delete a custom company from benchmark."""
    success = delete_custom_company_record(company_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Custom company '{company_name}' not found or cannot be deleted")
    return {"status": "ok", "deleted": company_name}


@app.get("/api/sample-apple")
def audit_sample_apple():
    """Audit the bundled Apple Environmental Progress Report 2024 PDF sample."""
    sample_path = ROOT / "data" / "sample_reports" / "apple_environmental_progress_report_2024_sample.pdf"
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="Apple sample PDF report not found")
        
    with open(sample_path, "rb") as f:
        content = f.read()
        
    parsed_doc = parse_pdf(content, filename=sample_path.name)
    agent = GreenwashAgent(provider="Mock Offline Fallback", retriever=retriever)
    doc_result = agent.audit_document(
        parsed_doc,
        company_name="Apple Inc.",
        sector="Consumer Hardware & Tech",
        max_claims=12,
    )
    doc_result["report_title"] = "Apple Environmental Progress Report 2024 (Sample)"
    doc_result["report_year"] = 2024
    doc_result["ticker"] = "AAPL"
    doc_result["country"] = "United States"
    # Auto-save to benchmark
    save_custom_company_record(doc_result)
    return doc_result


@app.post("/api/audit/claim")
def audit_single_claim(payload: AuditTextRequest):
    """Live RAG tester: dissect a single environmental sentence against the 4 pillars."""
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Claim text cannot be empty")

    agent = GreenwashAgent(
        provider=payload.provider or "Mock Offline Fallback",
        api_key=payload.api_key or "",
        model=payload.model or "",
        retriever=retriever,
    )
    result = agent.audit_text(text)
    return result


@app.post("/api/audit/pdf")
async def audit_pdf_report(
    file: UploadFile = File(...),
    company_name: Optional[str] = Form(""),
    sector: Optional[str] = Form(""),
    provider: Optional[str] = Form("Mock Offline Fallback"),
    api_key: Optional[str] = Form(""),
    model: Optional[str] = Form(""),
    max_claims: Optional[int] = Form(10),
    auto_save: Optional[bool] = Form(True),
):
    """Upload and audit a corporate sustainability report PDF."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    content = await file.read()
    try:
        parsed_doc = parse_pdf(content, filename=file.filename)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse PDF: {str(exc)}")

    agent = GreenwashAgent(
        provider=provider or "Mock Offline Fallback",
        api_key=api_key or "",
        model=model or "",
        retriever=retriever,
    )

    doc_result = agent.audit_document(
        parsed_doc,
        company_name=company_name or "",
        sector=sector or "",
        max_claims=max_claims or 10,
    )
    
    # Auto save to benchmark if requested
    if auto_save:
        save_custom_company_record(doc_result)
        doc_result["saved_to_benchmark"] = True
        
    return doc_result


@app.get("/api/standards")
def get_standards():
    """Get list of indexed standards in the knowledge base."""
    return {
        "total_chunks": len(retriever.chunks),
        "standards": [
            {"id": c.id, "tag": c.tag, "standard": c.standard, "title": c.title, "preview": c.body[:250]}
            for c in retriever.chunks
        ],
    }


@app.get("/api/taxonomy")
def get_taxonomy():
    """Get the 4 Pillars Greenwashing Taxonomy."""
    return taxonomy_data


# ---------------------------------------------------------------------------
# Static frontend delivery (mounts frontend folder if present)
# ---------------------------------------------------------------------------
FRONTEND_DIR = ROOT / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def serve_frontend():
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend_root")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"\n[GreenWash-Screener] FastAPI Server starting on http://{host}:{port} ...")
    uvicorn.run("server:app", host=host, port=port, reload=False)
