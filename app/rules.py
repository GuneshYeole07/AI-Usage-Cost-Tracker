"""Waste-detection rules.

Every rule is deterministic and explainable: it returns the evidence it used,
how many tokens / dollars were avoidable, and a concrete fix. Estimates are
deliberately conservative — when in doubt a rule under-counts.

Rules never double-count the same tokens:
- long_context counts only the history a fresh start would have dropped;
- tool_overhead only counts turns *below* the long-context threshold;
- model_choice and cache_miss save money, not tokens (tokens_wasted = 0).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field

from app.config import Settings, settings
from app.models import AgentSession, Turn
from app.pricing import DOWNGRADE, family, price_for, turn_cost, turn_input_cost


@dataclass
class Finding:
    session_id: str
    user: str
    rule: str
    title: str
    severity: str  # low | medium | high
    tokens_wasted: int
    cost_wasted: float
    evidence: str
    fix: str
    turns: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["cost_wasted"] = round(self.cost_wasted, 4)
        return d


RULES_INFO = {
    "long_context": {
        "title": "Chat ran too long",
        "what": "Every message resends the whole history. Past a point, a fresh session with a short summary is far cheaper.",
    },
    "agent_loop": {
        "title": "Agent stuck in a loop",
        "what": "The agent kept retrying failing tool calls. After 2 failed attempts, more retries rarely help.",
    },
    "repeated_reads": {
        "title": "Same files read again and again",
        "what": "The agent re-read the same file several times, paying for its full size each time.",
    },
    "tool_overhead": {
        "title": "Heavy startup context",
        "what": "Too many tools / MCP servers or a bloated CLAUDE.md make every single message heavier.",
    },
    "model_choice": {
        "title": "Big model for a small task",
        "what": "A short task with little output ran on the most expensive model; a cheaper model would do.",
    },
    "cache_miss": {
        "title": "Prompt cache not working",
        "what": "Long pauses let the prompt cache expire, so history was paid at full price instead of cache price.",
    },
}


def _cost(t: Turn) -> float:
    return turn_cost(t.model, t.input_tokens, t.output_tokens, t.cache_creation_tokens, t.cache_read_tokens)


def _k(n: float) -> str:
    return f"{n / 1000:.0f}k" if n >= 1000 else str(int(n))


def rule_long_context(s: AgentSession, cfg: Settings) -> Finding | None:
    """Counterfactual: what if the user had started fresh each time context crossed the threshold?

    A fresh session doesn't stay small forever — it regrows at the same pace — so the
    saving on each turn is only the history that a reset would have dropped (`offset`),
    not the whole context. Real compactions (context suddenly shrinking) reset the offset.

    The turn that crosses the threshold is already sent when the user could react, so the
    reset happens *after* it: each turn only saves what earlier resets would have dropped.
    """
    # A fresh session restarts with the same setup, so it can't be smaller than this one's first message.
    baseline = max(cfg.FRESH_SESSION_BASELINE, s.turns[0].context_tokens)
    offset = 0
    prev = 0
    waste = 0
    cost = 0.0
    flagged: list[Turn] = []
    first_cross: int | None = None
    for t in s.turns:
        ctx = t.context_tokens
        if prev and ctx < prev * 0.6:  # the user (or auto-compact) already reset here
            offset = 0
        # Saving on this turn comes only from resets made before it.
        offset = min(offset, max(0, ctx - baseline))
        if offset > 0 and ctx > 0:
            waste += offset
            cost += turn_input_cost(t.model, t.input_tokens, t.cache_creation_tokens, t.cache_read_tokens) * offset / ctx
            flagged.append(t)
        # Crossing the threshold here means a reset right after this turn.
        if ctx - offset > cfg.LONG_CONTEXT_THRESHOLD:
            offset = ctx - baseline
            if first_cross is None:
                first_cross = t.idx
        prev = ctx
    if waste < cfg.LONG_CONTEXT_MIN_WASTE or first_cross is None:
        return None
    peak = max(t.context_tokens for t in s.turns)
    return Finding(
        session_id=s.id,
        user=s.user,
        rule="long_context",
        title=RULES_INFO["long_context"]["title"],
        severity="high" if waste > 1_000_000 else "medium",
        tokens_wasted=int(waste),
        cost_wasted=cost,
        evidence=(
            f"Context passed {_k(cfg.LONG_CONTEXT_THRESHOLD)} at turn {first_cross + 1} and peaked at {_k(peak)}. "
            f"Starting fresh at that point would have made {len(flagged)} later messages lighter."
        ),
        fix="Start a new session when a subtask is done (or run /compact) and carry over a 5-line summary instead of the whole chat.",
        turns=[t.idx for t in flagged],
    )


def rule_agent_loop(s: AgentSession, cfg: Settings) -> Finding | None:
    runs: list[list[Turn]] = []
    current: list[Turn] = []
    for t in s.turns:
        if t.tool_errors > 0:
            current.append(t)
        else:
            if len(current) >= cfg.LOOP_MIN_CONSECUTIVE_ERRORS:
                runs.append(current)
            current = []
    if len(current) >= cfg.LOOP_MIN_CONSECUTIVE_ERRORS:
        runs.append(current)
    if not runs:
        return None
    wasted_turns = [t for run in runs for t in run[cfg.LOOP_ALLOWED_RETRIES :]]
    waste = sum(t.total_tokens for t in wasted_turns)
    cost = sum(_cost(t) for t in wasted_turns)
    longest = max(runs, key=len)
    return Finding(
        session_id=s.id,
        user=s.user,
        rule="agent_loop",
        title=RULES_INFO["agent_loop"]["title"],
        severity="high" if len(longest) >= 8 else "medium",
        tokens_wasted=int(waste),
        cost_wasted=cost,
        evidence=(
            f"{len(runs)} loop(s) of failing tool calls; the longest ran {len(longest)} turns in a row "
            f"(turns {longest[0].idx + 1}–{longest[-1].idx + 1}). Retries beyond the first {cfg.LOOP_ALLOWED_RETRIES} counted as waste."
        ),
        fix="Stop the agent after 2 failed attempts. Read the error yourself and give one specific hint, or fix that step by hand.",
        turns=[t.idx for run in runs for t in run],
    )


def rule_repeated_reads(s: AgentSession, cfg: Settings) -> Finding | None:
    seen: Counter[str] = Counter()
    waste = 0
    wasted_turns: set[int] = set()
    for t in s.turns:
        for r in t.file_reads or []:
            seen[r["file"]] += 1
            if seen[r["file"]] > cfg.REREAD_ALLOWED:
                waste += int(r.get("tokens", 0))
                wasted_turns.add(t.idx)
    if waste < 5_000:
        return None
    repeated = {f: n for f, n in seen.items() if n > cfg.REREAD_ALLOWED}
    worst = max(repeated.values())
    # Price re-read tokens at the cheapest model-input rate seen in the session (conservative).
    rate = min(price_for(t.model).input for t in s.turns)
    return Finding(
        session_id=s.id,
        user=s.user,
        rule="repeated_reads",
        title=RULES_INFO["repeated_reads"]["title"],
        severity="medium" if waste > 50_000 else "low",
        tokens_wasted=waste,
        cost_wasted=waste * rate / 1_000_000,
        evidence=f"{len(repeated)} file(s) were read more than {cfg.REREAD_ALLOWED} times; one file was read {worst} times.",
        fix="Point the agent at exact files and functions (@file, line numbers) instead of asking it to re-check everything.",
        turns=sorted(wasted_turns),
    )


def rule_tool_overhead(s: AgentSession, cfg: Settings) -> Finding | None:
    first = s.turns[0].context_tokens
    if first <= cfg.TOOL_OVERHEAD_THRESHOLD:
        return None
    excess = first - cfg.LEAN_STARTUP_CONTEXT
    owned = [t for t in s.turns if t.context_tokens <= cfg.LONG_CONTEXT_THRESHOLD]
    if not owned:
        return None
    waste = excess * len(owned)
    # Startup context is normally cached, so price it at cache-read rate.
    cost = sum(excess * price_for(t.model).input * price_for(t.model).cache_read_mult / 1_000_000 for t in owned)
    return Finding(
        session_id=s.id,
        user=s.user,
        rule="tool_overhead",
        title=RULES_INFO["tool_overhead"]["title"],
        severity="low" if waste < 300_000 else "medium",
        tokens_wasted=int(waste),
        cost_wasted=cost,
        evidence=(
            f"The very first message already carried {_k(first)} tokens (a lean setup is ~{_k(cfg.LEAN_STARTUP_CONTEXT)}). "
            f"That extra {_k(excess)} rode along on {len(owned)} messages."
        ),
        fix="Disable MCP servers and tools you don't use in this project and trim CLAUDE.md to what the agent actually needs.",
        turns=[t.idx for t in owned],
    )


def rule_model_choice(s: AgentSession, cfg: Settings) -> Finding | None:
    if len(s.turns) > cfg.SMALL_TASK_MAX_TURNS:
        return None
    total_out = sum(t.output_tokens for t in s.turns)
    if total_out > cfg.SMALL_TASK_MAX_OUTPUT:
        return None
    fams = {family(t.model) for t in s.turns}
    big = [f for f in fams if f in DOWNGRADE]
    if not big:
        return None
    actual = sum(_cost(t) for t in s.turns)
    alt = sum(
        turn_cost(
            DOWNGRADE.get(family(t.model), t.model),
            t.input_tokens,
            t.output_tokens,
            t.cache_creation_tokens,
            t.cache_read_tokens,
        )
        for t in s.turns
    )
    saving = actual - alt
    if saving <= 0.001:
        return None
    model = s.turns[0].model
    alt_name = DOWNGRADE.get(family(model), "a smaller model")
    return Finding(
        session_id=s.id,
        user=s.user,
        rule="model_choice",
        title=RULES_INFO["model_choice"]["title"],
        severity="low",
        tokens_wasted=0,
        cost_wasted=saving,
        evidence=f"Small task ({len(s.turns)} turns, {total_out} output tokens) ran on {model}.",
        fix=f"Use {alt_name.title()} for quick edits and questions (switch with /model); keep the top model for hard problems.",
        turns=[t.idx for t in s.turns],
    )


def rule_cache_miss(s: AgentSession, cfg: Settings) -> Finding | None:
    if len(s.turns) < cfg.CACHE_MIN_TURNS:
        return None
    total_in = sum(t.context_tokens for t in s.turns)
    if total_in == 0:
        return None
    hit = sum(t.cache_read_tokens for t in s.turns) / total_in
    if hit >= cfg.CACHE_MIN_HIT_RATIO:
        return None
    uncached = sum(t.input_tokens + t.cache_creation_tokens for t in s.turns)
    avoidable = max(0, uncached - 0.15 * total_in)  # healthy sessions still write ~15% fresh
    p = price_for(s.turns[0].model)
    saving = avoidable * p.input * (p.cache_write_mult - p.cache_read_mult) / 1_000_000
    if saving <= 0.001:
        return None
    return Finding(
        session_id=s.id,
        user=s.user,
        rule="cache_miss",
        title=RULES_INFO["cache_miss"]["title"],
        severity="medium" if saving > 1 else "low",
        tokens_wasted=0,
        cost_wasted=saving,
        evidence=f"Only {hit:.0%} of input came from the cache over {len(s.turns)} turns (healthy long sessions are 80%+).",
        fix="Avoid long breaks (5+ min) in the middle of a session, or start fresh after a break; keep CLAUDE.md stable mid-session.",
        turns=[],
    )


ALL_RULES = [
    rule_long_context,
    rule_agent_loop,
    rule_repeated_reads,
    rule_tool_overhead,
    rule_model_choice,
    rule_cache_miss,
]


def analyze_session(s: AgentSession, cfg: Settings | None = None) -> list[Finding]:
    cfg = cfg or settings
    if not s.turns:
        return []
    out = []
    for rule in ALL_RULES:
        f = rule(s, cfg)
        if f is not None:
            out.append(f)
    return out
