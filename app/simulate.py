"""SIMULATED team data for demos.

Six fictional developers, each with a different habit, over the last 21 days.
Everything generated here is flagged is_simulated=True and shown with a
"simulated data" banner in the dashboard. It is NOT real company data.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AgentSession, Label, Turn
from app.parser import hash_path

DEVS = [
    ("aarav", "marathon"),  # never starts a fresh chat
    ("diya", "opus_everything"),  # top model for every small thing
    ("kabir", "loop_prone"),  # lets the agent retry forever
    ("meera", "efficient"),  # good habits
    ("rohan", "tool_hoarder"),  # 15 MCP servers connected
    ("sana", "long_breaks"),  # pauses mid-session, cache expires
]
PROJECTS = ["client-portal", "payments-api", "mobile-app", "marketing-site"]
AUTO_COMPACT_AT = 165_000
OPUS, SONNET, HAIKU = "claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5"


def _pick_task(rng: random.Random, habit: str) -> str:
    if habit == "marathon":
        return rng.choices(["small", "medium", "large"], [0.2, 0.3, 0.5])[0]
    return rng.choices(["small", "medium", "large"], [0.45, 0.4, 0.15])[0]


def _n_turns(rng: random.Random, task: str, habit: str) -> int:
    if task == "small":
        return rng.randint(2, 6)
    if task == "medium":
        return rng.randint(9, 24)
    if habit == "marathon":
        return rng.randint(60, 140)
    return rng.randint(10, 20) if habit == "efficient" else rng.randint(25, 55)


def _model(rng: random.Random, task: str, habit: str) -> str:
    if habit == "opus_everything":
        return OPUS
    if task == "small":
        return rng.choices([HAIKU, SONNET], [0.3, 0.7])[0]
    if task == "large":
        return rng.choices([OPUS, SONNET], [0.3, 0.7])[0]
    return SONNET


def _build_session(rng: random.Random, sid: str, user: str, habit: str, start: datetime) -> AgentSession:
    task = _pick_task(rng, habit)
    n = _n_turns(rng, task, habit)
    model = _model(rng, task, habit)
    project = rng.choice(PROJECTS)
    startup = rng.randint(72_000, 90_000) if habit == "tool_hoarder" else rng.randint(45_000, 55_000)

    # File pool: fewer distinct files => more re-reads.
    pool_size = 4 if habit in ("loop_prone", "marathon") else 14
    files = [(hash_path(f"{project}/src/file_{i}.py"), rng.randint(800, 5_000)) for i in range(pool_size)]

    # Plan one failure loop for loop-prone devs on non-trivial tasks.
    loop_start, loop_len = -1, 0
    if habit == "loop_prone" and task != "small" and rng.random() < 0.6:
        loop_len = rng.randint(4, 10)
        loop_start = rng.randint(2, max(3, n - loop_len - 1))
        n = max(n, loop_start + loop_len + 1)

    gap_prob = 0.40 if habit == "long_breaks" else 0.03
    context = startup
    ts = start
    turns: list[Turn] = []
    for i in range(n):
        in_loop = loop_start <= i < loop_start + loop_len
        long_gap = i > 0 and rng.random() < gap_prob
        ts += timedelta(minutes=rng.randint(6, 25)) if long_gap else timedelta(seconds=rng.randint(15, 90))

        added = rng.randint(400, 3_000)
        reads = []
        if rng.random() < (0.55 if habit in ("loop_prone", "marathon") else 0.35):
            fhash, size = rng.choice(files)
            reads.append({"file": fhash, "tokens": size})
            added += size
        context += added

        # Real agents auto-compact when the context window fills up.
        compacted = context > AUTO_COMPACT_AT
        if compacted:
            context = rng.randint(25_000, 40_000)

        if i == 0 or long_gap or compacted:
            cache_read, cache_creation = 0, context
        else:
            cache_read, cache_creation = context - added, added
        output = rng.randint(60, 380) if task == "small" else rng.randint(180, 1_700)
        tool_calls = rng.randint(1, 3) if (in_loop or reads) else rng.randint(0, 2)
        errors = 1 if in_loop else (1 if tool_calls and rng.random() < 0.03 else 0)
        names = ["Read"] * len(reads) + rng.choices(["Bash", "Edit", "Grep", "Write"], k=max(0, tool_calls - len(reads)))

        turns.append(
            Turn(
                idx=i,
                timestamp=ts,
                model=model,
                input_tokens=rng.randint(3, 25),
                output_tokens=output,
                cache_creation_tokens=cache_creation,
                cache_read_tokens=cache_read,
                tool_calls=max(tool_calls, len(reads)),
                tool_errors=errors,
                tool_names=names,
                file_reads=reads,
            )
        )
        context += output

    s = AgentSession(
        id=sid,
        user=user,
        project=project,
        source="simulated",
        is_simulated=True,
        task_type=task,
        started_at=turns[0].timestamp,
        ended_at=turns[-1].timestamp,
    )
    s.turns = turns
    return s


def generate(days: int = 21, seed: int = 7, now: datetime | None = None) -> list[AgentSession]:
    rng = random.Random(seed)
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    sessions: list[AgentSession] = []
    for d in range(days - 1, -1, -1):
        day = today - timedelta(days=d)
        weekend = day.weekday() >= 5
        for user, habit in DEVS:
            if weekend and rng.random() < 0.75:
                continue
            for k in range(rng.randint(1, 2) if weekend else rng.randint(2, 5)):
                # 04:30–13:30 UTC is roughly a 10:00–19:00 working day in India.
                start = day + timedelta(hours=4, minutes=30) + timedelta(minutes=rng.randint(0, 9 * 60))
                if start > now:
                    continue
                sessions.append(_build_session(rng, f"sim-{user}-{day:%Y%m%d}-{k}", user, habit, start))
    return sessions


def clear_simulated(db: Session) -> int:
    ids = list(db.scalars(select(AgentSession.id).where(AgentSession.is_simulated.is_(True))))
    if not ids:
        return 0
    db.execute(delete(Label).where(Label.session_id.in_(ids)))
    for s in db.scalars(select(AgentSession).where(AgentSession.is_simulated.is_(True))):
        db.delete(s)
    db.commit()
    return len(ids)


def seed_demo_data(db: Session, days: int = 21, seed: int = 7) -> dict:
    """Idempotent: wipes previous simulated data, then inserts a fresh set."""
    removed = clear_simulated(db)
    sessions = generate(days=days, seed=seed)
    db.add_all(sessions)
    db.commit()
    return {"removed": removed, "sessions": len(sessions), "turns": sum(len(s.turns) for s in sessions)}
