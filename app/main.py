"""FastAPI backend for the LLM Token Auditor."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import analytics
from app.config import settings
from app.database import get_db, init_db
from app.models import AgentSession, Label, Turn
from app.parser import parse_claude_code
from app.rules import RULES_INFO
from app.simulate import clear_simulated, seed_demo_data

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
log = logging.getLogger("auditor")

Source = Literal["all", "real", "simulated"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    log.info("Database ready at %s", settings.DATABASE_URL)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Finds where AI coding-agent tokens are wasted, explains why, and estimates the savings. "
    "Stores metadata only — never prompt or response text.",
    lifespan=lifespan,
)


# ---------- Schemas ----------
class TurnIn(BaseModel):
    timestamp: datetime
    model: str = Field(min_length=1, max_length=64)
    input_tokens: int = Field(0, ge=0)
    output_tokens: int = Field(0, ge=0)
    cache_creation_tokens: int = Field(0, ge=0)
    cache_read_tokens: int = Field(0, ge=0)
    tool_calls: int = Field(0, ge=0)
    tool_errors: int = Field(0, ge=0)


class SessionIn(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    user: str = Field(min_length=1, max_length=64)
    project: str = Field("unknown", max_length=64)
    source: str = Field("api", max_length=32)
    turns: list[TurnIn] = Field(min_length=1)

    @field_validator("user", "project")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip().lower()


class LabelIn(BaseModel):
    session_id: str
    rule: str
    is_waste: bool
    note: str | None = Field(None, max_length=500)


def _naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _save_sessions(db: Session, sessions: list[AgentSession]) -> tuple[int, int]:
    """Insert sessions, replacing any with the same id (re-imports are idempotent)."""
    new, replaced = 0, 0
    for s in sessions:
        existing = db.get(AgentSession, s.id)
        if existing:
            db.delete(existing)
            db.flush()
            replaced += 1
        else:
            new += 1
        db.add(s)
    db.commit()
    return new, replaced


# ---------- System ----------
@app.get("/health", tags=["system"])
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover
        raise HTTPException(503, f"database unavailable: {exc}") from exc
    return {
        "status": "ok",
        "version": settings.VERSION,
        "sessions": db.scalar(select(func.count()).select_from(AgentSession)),
        "turns": db.scalar(select(func.count()).select_from(Turn)),
    }


@app.get("/rules", tags=["system"])
def rules():
    """The waste rules and the thresholds they use — nothing is a black box."""
    return {
        "rules": [{"rule": k, **v} for k, v in RULES_INFO.items()],
        "thresholds": {
            k: getattr(settings, k)
            for k in (
                "LONG_CONTEXT_THRESHOLD",
                "FRESH_SESSION_BASELINE",
                "LONG_CONTEXT_MIN_WASTE",
                "LOOP_MIN_CONSECUTIVE_ERRORS",
                "LOOP_ALLOWED_RETRIES",
                "REREAD_ALLOWED",
                "TOOL_OVERHEAD_THRESHOLD",
                "LEAN_STARTUP_CONTEXT",
                "SMALL_TASK_MAX_TURNS",
                "SMALL_TASK_MAX_OUTPUT",
                "CACHE_MIN_TURNS",
                "CACHE_MIN_HIT_RATIO",
            )
        },
    }


# ---------- Ingestion ----------
@app.post("/import/claude-code", tags=["ingest"])
async def import_claude_code(
    files: list[UploadFile] = File(...),
    user: str = Form("me"),
    db: Session = Depends(get_db),
):
    """Upload Claude Code session logs (.jsonl). Only metadata is kept."""
    user = user.strip().lower() or "me"
    totals = {"files": 0, "sessions_new": 0, "sessions_replaced": 0, "turns": 0, "bad_lines": 0, "empty_files": 0}
    for f in files:
        raw = await f.read()
        lines = raw.decode("utf-8", errors="replace").splitlines()
        sessions, report = parse_claude_code(lines, user=user)
        new, replaced = _save_sessions(db, sessions)
        totals["files"] += 1
        totals["sessions_new"] += new
        totals["sessions_replaced"] += replaced
        totals["turns"] += report.turns
        totals["bad_lines"] += report.bad_lines
        totals["empty_files"] += 0 if sessions else 1
    log.info("Imported %s", totals)
    return totals


@app.post("/sessions", status_code=201, tags=["ingest"])
def create_session(payload: SessionIn, db: Session = Depends(get_db)):
    """Generic ingestion for API/proxy traffic or other agents."""
    turns = sorted(payload.turns, key=lambda t: t.timestamp)
    s = AgentSession(
        id=payload.id,
        user=payload.user,
        project=payload.project,
        source=payload.source,
        is_simulated=False,
        started_at=_naive_utc(turns[0].timestamp),
        ended_at=_naive_utc(turns[-1].timestamp),
    )
    s.turns = [
        Turn(idx=i, tool_names=[], file_reads=[], **{**t.model_dump(), "timestamp": _naive_utc(t.timestamp)})
        for i, t in enumerate(turns)
    ]
    _save_sessions(db, [s])
    return {"id": s.id, "turns": len(s.turns)}


@app.post("/demo/seed", tags=["demo"])
def demo_seed(db: Session = Depends(get_db)):
    """(Re)create the SIMULATED team dataset. Safe to call repeatedly."""
    return seed_demo_data(db)


@app.delete("/demo", tags=["demo"])
def demo_clear(db: Session = Depends(get_db)):
    return {"removed": clear_simulated(db)}


@app.delete("/sessions", tags=["ingest"])
def delete_real_sessions(db: Session = Depends(get_db)):
    """Delete all imported (non-simulated) sessions."""
    rows = list(db.scalars(select(AgentSession).where(AgentSession.is_simulated.is_(False))))
    for s in rows:
        db.delete(s)
    db.commit()
    return {"removed": len(rows)}


# ---------- Analytics ----------
def _stats(db: Session, user: str | None, source: Source):
    return analytics.load_stats(db, user=user or None, source=source)


@app.get("/overview", tags=["analytics"])
def get_overview(user: str | None = None, source: Source = "all", db: Session = Depends(get_db)):
    return analytics.overview(_stats(db, user, source))


@app.get("/daily", tags=["analytics"])
def get_daily(user: str | None = None, source: Source = "all", db: Session = Depends(get_db)):
    return analytics.daily(_stats(db, user, source))


@app.get("/users", tags=["analytics"])
def get_users(source: Source = "all", db: Session = Depends(get_db)):
    return analytics.by_user(_stats(db, None, source))


@app.get("/findings", tags=["analytics"])
def get_findings(
    user: str | None = None,
    rule: str | None = None,
    source: Source = "all",
    limit: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    if rule and rule not in RULES_INFO:
        raise HTTPException(422, f"unknown rule '{rule}'. Valid: {', '.join(RULES_INFO)}")
    rows = []
    for st in _stats(db, user, source):
        for f in st.findings:
            if rule and f.rule != rule:
                continue
            rows.append(
                {**f.to_dict(), "project": st.session.project, "started_at": st.session.started_at.isoformat()}
            )
    rows.sort(key=lambda r: (r["cost_wasted"], r["tokens_wasted"]), reverse=True)
    return rows[:limit]


@app.get("/sessions", tags=["analytics"])
def list_sessions(
    user: str | None = None,
    source: Source = "all",
    sort: Literal["waste", "recent", "tokens"] = "waste",
    limit: int = Query(100, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    rows = [analytics.session_row(st) for st in _stats(db, user, source)]
    key = {"waste": "waste_cost", "recent": "started_at", "tokens": "total_tokens"}[sort]
    rows.sort(key=lambda r: r[key], reverse=True)
    return rows[:limit]


@app.get("/sessions/{session_id}", tags=["analytics"])
def get_session(session_id: str, db: Session = Depends(get_db)):
    for st in analytics.load_stats(db):
        if st.session.id == session_id:
            return analytics.session_detail(st)
    raise HTTPException(404, "session not found")


@app.get("/forecast", tags=["analytics"])
def get_forecast(
    budget: int | None = Query(None, gt=0, description="Monthly team token budget"),
    source: Source = "all",
    db: Session = Depends(get_db),
):
    return analytics.forecast(_stats(db, None, source), budget=budget)


# ---------- Validation (are the rules actually right?) ----------
@app.get("/validation", tags=["validation"])
def get_validation(source: Source = "all", db: Session = Depends(get_db)):
    return analytics.validation(db, _stats(db, None, source))


@app.post("/labels", tags=["validation"])
def upsert_label(payload: LabelIn, db: Session = Depends(get_db)):
    if payload.rule not in RULES_INFO:
        raise HTTPException(422, f"unknown rule '{payload.rule}'")
    if not db.get(AgentSession, payload.session_id):
        raise HTTPException(404, "session not found")
    lb = db.scalar(select(Label).where(Label.session_id == payload.session_id, Label.rule == payload.rule))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if lb:
        lb.is_waste, lb.note, lb.created_at = payload.is_waste, payload.note, now
    else:
        db.add(Label(created_at=now, **payload.model_dump()))
    db.commit()
    return {"ok": True}


@app.delete("/labels", tags=["validation"])
def clear_labels(db: Session = Depends(get_db)):
    n = db.query(Label).delete()
    db.commit()
    return {"removed": n}
