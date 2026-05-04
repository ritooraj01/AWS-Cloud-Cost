"""
Cloud Cost Panic Button — FastAPI Application
Session-based: CSV is uploaded, analyzed in-memory, results cached per session.
"""

import uuid
import os
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.parsers import aws_parser
from backend import insights_engine

app = FastAPI(
    title="Cloud Cost Panic Button",
    description="Explain your AWS bill in plain English.",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# CORS — required for GitHub Pages frontend calling Render backend
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # restrict to your GitHub Pages domain after launch
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store: { session_id: insights_payload }
_sessions: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Static files (frontend)
# ---------------------------------------------------------------------------
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serve the frontend dashboard."""
    index = FRONTEND_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Frontend not found.")
    return HTMLResponse(content=index.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    """
    Accept an AWS billing CSV, parse it, run all analyzers, return session_id.
    The frontend then calls GET /analysis/{session_id} to get the full payload.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > 50 * 1024 * 1024:  # 50 MB hard limit
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 50 MB.")

    try:
        parsed = aws_parser.parse(content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected parse error: {exc}")

    try:
        payload = insights_engine.generate(parsed)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis error: {exc}")

    session_id = str(uuid.uuid4())
    _sessions[session_id] = payload

    # Keep memory bounded: evict oldest if > 100 sessions
    if len(_sessions) > 100:
        oldest = next(iter(_sessions))
        del _sessions[oldest]

    return JSONResponse({"session_id": session_id, "status": "ok"})


@app.post("/upload-multi")
async def upload_multi_csv(
    file1: UploadFile = File(...),
    file2: UploadFile = File(...),
):
    """
    Accept two billing CSVs (e.g. current + previous month) for side-by-side
    comparison.  Merges records from both files; the breakdown analyzer
    automatically splits them by calendar month.
    """
    parsed_list = []
    for f in (file1, file2):
        if not f.filename.endswith(".csv"):
            raise HTTPException(status_code=400, detail="Only .csv files are supported.")
        content = await f.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail=f"{f.filename} is empty.")
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"{f.filename} exceeds 50 MB limit.")
        try:
            parsed_list.append(aws_parser.parse(content))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"{f.filename}: {exc}")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Parse error in {f.filename}: {exc}")

    # Sort so the older file is first
    parsed_list.sort(key=lambda p: p["date_range"]["start"])
    older, newer = parsed_list[0], parsed_list[1]

    merged = {
        "records":    older["records"] + newer["records"],
        "days_count": older["days_count"] + newer["days_count"],
        "date_range": {
            "start": older["date_range"]["start"],
            "end":   newer["date_range"]["end"],
        },
        "services": sorted(set(older["services"] + newer["services"])),
        "regions":  sorted(set(older["regions"]  + newer["regions"])),
        "errors":   older["errors"] + newer["errors"],
        "format":   newer["format"],
        "currency": newer["currency"],
    }

    try:
        payload = insights_engine.generate(merged)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis error: {exc}")

    session_id = str(uuid.uuid4())
    _sessions[session_id] = payload

    if len(_sessions) > 100:
        oldest = next(iter(_sessions))
        del _sessions[oldest]

    return JSONResponse({"session_id": session_id, "status": "ok", "mode": "comparison"})


@app.get("/analysis/{session_id}")
async def get_analysis(session_id: str):
    """Return full insights payload for a session."""
    payload = _sessions.get(session_id)
    if not payload:
        raise HTTPException(
            status_code=404,
            detail="Session not found. Please re-upload your CSV.",
        )
    return JSONResponse(payload)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "Cloud Cost Panic Button"}
