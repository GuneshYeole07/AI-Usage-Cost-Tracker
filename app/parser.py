"""Parser for Claude Code session logs (~/.claude/projects/<project>/<session>.jsonl).

Only metadata is extracted: token usage, model, tool names, tool error flags and
the *size* of files the agent read. File paths are hashed; text is never kept.

Format notes (handled defensively, unknown lines are skipped):
- Each line is a JSON record with `type` ("user" | "assistant" | others), `sessionId`,
  `timestamp`, `cwd`.
- One API response can be written as several "assistant" lines sharing the same
  `message.id` (one per content block) — we de-duplicate by message id so usage is
  counted once.
- Tool calls are `tool_use` blocks in assistant content; their results arrive as
  `tool_result` blocks (with `is_error`) in the next "user" line.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import PurePath

from app.models import AgentSession, Turn

READ_TOOLS = {"Read", "read_file", "View"}


def hash_path(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _text_len(content) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(b.get("text", "")) for b in content if isinstance(b, dict))
    return 0


@dataclass
class ParseReport:
    lines: int = 0
    bad_lines: int = 0
    sessions: int = 0
    turns: int = 0
    skipped_sessions: int = 0
    errors: list[str] = field(default_factory=list)


def parse_claude_code(lines: Iterable[str], user: str) -> tuple[list[AgentSession], ParseReport]:
    report = ParseReport()
    # session_id -> {"turns": {message_id: Turn}, "cwd": str}
    sessions: dict[str, dict] = {}
    tool_index: dict[str, tuple[Turn, str, str | None]] = {}  # tool_use_id -> (turn, tool name, file hash)

    for raw in lines:
        report.lines += 1
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            report.bad_lines += 1
            continue
        if not isinstance(rec, dict):
            report.bad_lines += 1
            continue

        sid = rec.get("sessionId")
        rtype = rec.get("type")
        if not sid or rtype not in ("assistant", "user"):
            continue
        bucket = sessions.setdefault(sid, {"turns": {}, "cwd": rec.get("cwd")})
        if not bucket["cwd"] and rec.get("cwd"):
            bucket["cwd"] = rec["cwd"]
        msg = rec.get("message") or {}
        content = msg.get("content")

        if rtype == "assistant":
            model = msg.get("model") or "unknown"
            if model == "<synthetic>":
                continue
            usage = msg.get("usage") or {}
            mid = msg.get("id") or rec.get("requestId") or rec.get("uuid")
            if not mid:
                continue
            turn = bucket["turns"].get(mid)
            if turn is None:
                ts = _parse_ts(rec.get("timestamp")) or datetime.now(timezone.utc).replace(tzinfo=None)
                turn = Turn(
                    idx=0,
                    timestamp=ts,
                    model=model,
                    input_tokens=int(usage.get("input_tokens") or 0),
                    output_tokens=int(usage.get("output_tokens") or 0),
                    cache_creation_tokens=int(usage.get("cache_creation_input_tokens") or 0),
                    cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
                    tool_calls=0,
                    tool_errors=0,
                    tool_names=[],
                    file_reads=[],
                )
                bucket["turns"][mid] = turn
            else:
                # Streaming writes can repeat usage; keep the largest output count seen.
                turn.output_tokens = max(turn.output_tokens, int(usage.get("output_tokens") or 0))

            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    name = block.get("name") or "unknown"
                    turn.tool_calls += 1
                    turn.tool_names = [*turn.tool_names, name]
                    fhash = None
                    inp = block.get("input") or {}
                    if name in READ_TOOLS and isinstance(inp, dict):
                        path = inp.get("file_path") or inp.get("path")
                        if path:
                            fhash = hash_path(str(path))
                    if block.get("id"):
                        tool_index[block["id"]] = (turn, name, fhash)

        elif rtype == "user" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                entry = tool_index.get(block.get("tool_use_id"))
                if not entry:
                    continue
                turn, name, fhash = entry
                if block.get("is_error"):
                    turn.tool_errors += 1
                elif fhash:
                    est_tokens = max(1, _text_len(block.get("content")) // 4)
                    turn.file_reads = [*turn.file_reads, {"file": fhash, "tokens": est_tokens}]

    result: list[AgentSession] = []
    for sid, bucket in sessions.items():
        turns = sorted(bucket["turns"].values(), key=lambda t: t.timestamp)
        if not turns:
            report.skipped_sessions += 1
            continue
        for i, t in enumerate(turns):
            t.idx = i
        cwd = bucket["cwd"]
        project = PurePath(cwd.replace("\\", "/")).name if cwd else "unknown"
        s = AgentSession(
            id=sid[:64],
            user=user,
            project=project or "unknown",
            source="claude_code",
            is_simulated=False,
            task_type=None,
            started_at=turns[0].timestamp,
            ended_at=turns[-1].timestamp,
        )
        s.turns = turns
        result.append(s)
        report.turns += len(turns)

    report.sessions = len(result)
    return result, report
