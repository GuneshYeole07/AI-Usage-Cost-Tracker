from datetime import datetime, timedelta

from app.models import AgentSession, Turn

T0 = datetime(2026, 11, 10, 5, 0, 0)


def make_session(contexts, *, model="claude-sonnet-4-5", outputs=None, errors=None, reads=None, cached=True, sid="s1"):
    """Build an in-memory session from a list of per-turn context sizes."""
    turns = []
    prev = 0
    for i, ctx in enumerate(contexts):
        new = max(ctx - prev, 0) if (cached and i > 0 and ctx >= prev) else ctx
        turns.append(
            Turn(
                idx=i,
                timestamp=T0 + timedelta(seconds=30 * i),
                model=model,
                input_tokens=0,
                output_tokens=(outputs[i] if outputs else 300),
                cache_creation_tokens=new,
                cache_read_tokens=ctx - new,
                tool_calls=1,
                tool_errors=(errors[i] if errors else 0),
                tool_names=["Bash"],
                file_reads=(reads[i] if reads else []),
            )
        )
        prev = ctx
    s = AgentSession(
        id=sid, user="tester", project="p", source="test", is_simulated=False,
        started_at=turns[0].timestamp, ended_at=turns[-1].timestamp,
    )
    s.turns = turns
    return s
