import json
import subprocess
import sys
import uuid
from pathlib import Path

HOOK = Path(__file__).parent.parent / "hooks" / "token_guard.py"


def _line(kind, **kw):
    if kind == "assistant":
        return json.dumps({"type": "assistant", "message": {"model": "claude-sonnet-4-5", "usage": {
            "input_tokens": 5, "output_tokens": 200, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": kw["ctx"]}}})
    return json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t", "is_error": kw["err"]}]}})


def _run(tmp_path, lines, session):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("\n".join(lines) + "\n")
    payload = json.dumps({"session_id": session, "transcript_path": str(transcript), "prompt": "hi"})
    out = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, timeout=30)
    assert out.returncode == 0
    return json.loads(out.stdout)["systemMessage"] if out.stdout.strip() else None


def test_quiet_on_small_chat(tmp_path):
    assert _run(tmp_path, [_line("assistant", ctx=30_000)], uuid.uuid4().hex) is None


def test_warns_on_long_chat_then_stays_quiet(tmp_path):
    lines = [_line("assistant", ctx=150_000)]
    session = uuid.uuid4().hex  # the hook remembers warnings per session id
    msg = _run(tmp_path, lines, session)
    assert msg and "151k" in msg and "/compact" in msg
    assert _run(tmp_path, lines, session) is None  # no nagging until it grows another step


def test_warns_on_failure_loop(tmp_path):
    lines = [_line("assistant", ctx=20_000)] + [_line("user", err=True)] * 5
    assert "failed in a row" in _run(tmp_path, lines, uuid.uuid4().hex)


def test_bad_input_never_breaks_the_user(tmp_path):
    out = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True, timeout=30)
    assert out.returncode == 0 and out.stdout == ""
