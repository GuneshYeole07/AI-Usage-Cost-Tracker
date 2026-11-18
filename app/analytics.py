"""Aggregations over sessions + findings (overview, team, daily, forecast, validation)."""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import AgentSession, Label
from app.pricing import turn_cost
from app.rules import RULES_INFO, Finding, analyze_session


@dataclass
class SessionStats:
    session: AgentSession
    findings: list[Finding]
    total_tokens: int
    cost: float
    peak_context: int

    @property
    def waste_tokens(self) -> int:
        return min(self.total_tokens, sum(f.tokens_wasted for f in self.findings))

    @property
    def waste_cost(self) -> float:
        return min(self.cost, sum(f.cost_wasted for f in self.findings))


def load_stats(db: Session, user: str | None = None, source: str = "all") -> list[SessionStats]:
    q = select(AgentSession).options(selectinload(AgentSession.turns)).order_by(AgentSession.started_at)
    if user:
        q = q.where(AgentSession.user == user)
    if source == "real":
        q = q.where(AgentSession.is_simulated.is_(False))
    elif source == "simulated":
        q = q.where(AgentSession.is_simulated.is_(True))
    out = []
    for s in db.scalars(q):
        if not s.turns:
            continue
        cost = sum(
            turn_cost(t.model, t.input_tokens, t.output_tokens, t.cache_creation_tokens, t.cache_read_tokens)
            for t in s.turns
        )
        out.append(
            SessionStats(
                session=s,
                findings=analyze_session(s),
                total_tokens=sum(t.total_tokens for t in s.turns),
                cost=cost,
                peak_context=max(t.context_tokens for t in s.turns),
            )
        )
    return out


def _pct(part: float, whole: float) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def overview(stats: list[SessionStats]) -> dict:
    total_tokens = sum(s.total_tokens for s in stats)
    total_cost = sum(s.cost for s in stats)
    waste_tokens = sum(s.waste_tokens for s in stats)
    waste_cost = sum(s.waste_cost for s in stats)

    by_rule: dict[str, dict] = {}
    for st in stats:
        for f in st.findings:
            r = by_rule.setdefault(
                f.rule,
                {"rule": f.rule, "title": f.title, "sessions": 0, "tokens_wasted": 0, "cost_wasted": 0.0, "fix": f.fix},
            )
            r["sessions"] += 1
            r["tokens_wasted"] += f.tokens_wasted
            r["cost_wasted"] += f.cost_wasted
    rules = sorted(by_rule.values(), key=lambda r: (r["cost_wasted"], r["tokens_wasted"]), reverse=True)
    for r in rules:
        r["cost_wasted"] = round(r["cost_wasted"], 2)
        r["what"] = RULES_INFO[r["rule"]]["what"]

    return {
        "sessions": len(stats),
        "turns": sum(len(s.session.turns) for s in stats),
        "users": len({s.session.user for s in stats}),
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 2),
        "waste_tokens": waste_tokens,
        "waste_cost": round(waste_cost, 2),
        "waste_token_pct": _pct(waste_tokens, total_tokens),
        "waste_cost_pct": _pct(waste_cost, total_cost),
        "sessions_with_waste": sum(1 for s in stats if s.findings),
        "has_simulated": any(s.session.is_simulated for s in stats),
        "has_real": any(not s.session.is_simulated for s in stats),
        "first_day": stats[0].session.started_at.date().isoformat() if stats else None,
        "last_day": stats[-1].session.started_at.date().isoformat() if stats else None,
        "by_rule": rules,
    }


def daily(stats: list[SessionStats]) -> list[dict]:
    days: dict[str, dict] = defaultdict(lambda: {"tokens": 0, "waste_tokens": 0, "cost": 0.0, "waste_cost": 0.0, "sessions": 0})
    for st in stats:
        d = days[st.session.started_at.date().isoformat()]
        d["tokens"] += st.total_tokens
        d["waste_tokens"] += st.waste_tokens
        d["cost"] += st.cost
        d["waste_cost"] += st.waste_cost
        d["sessions"] += 1
    return [
        {"date": k, **{m: (round(v, 2) if isinstance(v, float) else v) for m, v in d.items()}}
        for k, d in sorted(days.items())
    ]


def by_user(stats: list[SessionStats]) -> list[dict]:
    users: dict[str, dict] = {}
    rule_tokens: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for st in stats:
        u = users.setdefault(
            st.session.user,
            {"user": st.session.user, "sessions": 0, "tokens": 0, "waste_tokens": 0, "cost": 0.0, "waste_cost": 0.0},
        )
        u["sessions"] += 1
        u["tokens"] += st.total_tokens
        u["waste_tokens"] += st.waste_tokens
        u["cost"] += st.cost
        u["waste_cost"] += st.waste_cost
        for f in st.findings:
            rule_tokens[st.session.user][f.title] += f.cost_wasted
    out = []
    for name, u in users.items():
        top = max(rule_tokens[name].items(), key=lambda kv: kv[1])[0] if rule_tokens[name] else "—"
        out.append(
            {
                **u,
                "cost": round(u["cost"], 2),
                "waste_cost": round(u["waste_cost"], 2),
                "waste_token_pct": _pct(u["waste_tokens"], u["tokens"]),
                "waste_cost_pct": _pct(u["waste_cost"], u["cost"]),
                "tokens_per_session": int(u["tokens"] / u["sessions"]),
                "top_issue": top,
            }
        )
    return sorted(out, key=lambda u: u["waste_cost"], reverse=True)


def session_row(st: SessionStats) -> dict:
    s = st.session
    return {
        "id": s.id,
        "user": s.user,
        "project": s.project,
        "source": s.source,
        "is_simulated": s.is_simulated,
        "started_at": s.started_at.isoformat(),
        "minutes": round((s.ended_at - s.started_at).total_seconds() / 60, 1),
        "turns": len(s.turns),
        "model": s.turns[0].model,
        "total_tokens": st.total_tokens,
        "peak_context": st.peak_context,
        "cost": round(st.cost, 3),
        "waste_tokens": st.waste_tokens,
        "waste_cost": round(st.waste_cost, 3),
        "waste_token_pct": _pct(st.waste_tokens, st.total_tokens),
        "rules": [f.rule for f in st.findings],
    }


def session_detail(st: SessionStats) -> dict:
    return {
        **session_row(st),
        "findings": [f.to_dict() for f in st.findings],
        "turn_data": [
            {
                "turn": t.idx + 1,
                "timestamp": t.timestamp.isoformat(),
                "model": t.model,
                "context_tokens": t.context_tokens,
                "cache_read_tokens": t.cache_read_tokens,
                "output_tokens": t.output_tokens,
                "tool_calls": t.tool_calls,
                "tool_errors": t.tool_errors,
            }
            for t in st.session.turns
        ],
    }


def forecast(stats: list[SessionStats], budget: int | None = None, now: datetime | None = None) -> dict:
    budget = budget or settings.MONTHLY_TOKEN_BUDGET
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    week_ago = now - timedelta(days=7)

    mtd = sum(s.total_tokens for s in stats if s.session.started_at >= month_start)
    last7 = sum(s.total_tokens for s in stats if s.session.started_at >= week_ago)
    last7_waste = sum(s.waste_tokens for s in stats if s.session.started_at >= week_ago)
    daily_rate = last7 / 7
    waste_share = last7_waste / last7 if last7 else 0.0
    remaining_days = days_in_month - now.day
    projected = mtd + daily_rate * remaining_days
    projected_fixed = mtd + daily_rate * (1 - waste_share) * remaining_days

    def hit_day(rate: float) -> str | None:
        if mtd >= budget:
            return now.date().isoformat()
        if rate <= 0:
            return None
        days_needed = (budget - mtd) / rate
        if days_needed > remaining_days:
            return None
        return (now + timedelta(days=days_needed)).date().isoformat()

    return {
        "month": now.strftime("%B %Y"),
        "budget_tokens": budget,
        "month_to_date_tokens": int(mtd),
        "daily_rate_tokens": int(daily_rate),
        "waste_share_pct": round(100 * waste_share, 1),
        "projected_tokens": int(projected),
        "projected_tokens_with_fixes": int(projected_fixed),
        "projected_pct_of_budget": _pct(projected, budget),
        "projected_with_fixes_pct_of_budget": _pct(projected_fixed, budget),
        "budget_hit_date": hit_day(daily_rate),
        "budget_hit_date_with_fixes": hit_day(daily_rate * (1 - waste_share)),
        "day_of_month": now.day,
        "days_in_month": days_in_month,
    }


def validation(db: Session, stats: list[SessionStats]) -> dict:
    labels = {(lb.session_id, lb.rule): lb for lb in db.scalars(select(Label))}
    per_rule: dict[str, dict] = {}
    queue = []
    for st in stats:
        for f in st.findings:
            r = per_rule.setdefault(
                f.rule, {"rule": f.rule, "title": f.title, "findings": 0, "labeled": 0, "confirmed": 0}
            )
            r["findings"] += 1
            lb = labels.get((f.session_id, f.rule))
            if lb:
                r["labeled"] += 1
                r["confirmed"] += 1 if lb.is_waste else 0
            queue.append(
                {
                    **f.to_dict(),
                    "project": st.session.project,
                    "started_at": st.session.started_at.isoformat(),
                    "session_turns": len(st.session.turns),
                    "label": None if not lb else ("waste" if lb.is_waste else "not_waste"),
                }
            )
    rules = []
    for r in per_rule.values():
        r["precision_pct"] = _pct(r["confirmed"], r["labeled"]) if r["labeled"] else None
        rules.append(r)
    labeled = sum(r["labeled"] for r in rules)
    confirmed = sum(r["confirmed"] for r in rules)
    return {
        "labeled": labeled,
        "confirmed": confirmed,
        "precision_pct": _pct(confirmed, labeled) if labeled else None,
        "by_rule": sorted(rules, key=lambda r: r["findings"], reverse=True),
        "queue": queue,
    }
