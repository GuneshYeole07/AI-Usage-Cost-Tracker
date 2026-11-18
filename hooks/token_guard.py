#!/usr/bin/env python3
"""Token Guard — a live warning hook for Claude Code (stdlib only, no install needed).

Runs on every prompt you send (UserPromptSubmit hook). It reads the session's
token usage from the transcript and warns you *before* you waste more tokens:

  * the chat has grown past TOKEN_GUARD_WARN tokens (default 100k), or
  * the agent's last TOKEN_GUARD_LOOP tool calls all failed (default 4).

It reads token counts and error flags only. It never sends anything anywhere.

Install: add to ~/.claude/settings.json (use the full path to this file):

  {
    "hooks": {
      "UserPromptSubmit": [
        {"hooks": [{"type": "command", "command": "python /full/path/to/hooks/token_guard.py"}]}
      ]
    }
  }
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

WARN_AT = int(os.environ.get("TOKEN_GUARD_WARN", "100000"))
STEP = int(os.environ.get("TOKEN_GUARD_STEP", "40000"))  # warn again after this much more growth
LOOP_N = int(os.environ.get("TOKEN_GUARD_LOOP", "4"))


def read_transcript(path: str) -> tuple[int, int]:
    """Return (current context tokens, trailing consecutive failed tool results)."""
    context = 0
    results: list[bool] = []  # True = error
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                msg = rec.get("message") or {}
                if rec.get("type") == "assistant":
                    u = msg.get("usage") or {}
                    total = (
                        int(u.get("input_tokens") or 0)
                        + int(u.get("cache_creation_input_tokens") or 0)
                        + int(u.get("cache_read_input_tokens") or 0)
                        + int(u.get("output_tokens") or 0)
                    )
                    if total and msg.get("model") != "<synthetic>":
                        context = total
                elif rec.get("type") == "user" and isinstance(msg.get("content"), list):
                    for block in msg["content"]:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            results.append(bool(block.get("is_error")))
    except OSError:
        return 0, 0
    streak = 0
    for is_err in reversed(results):
        if not is_err:
            break
        streak += 1
    return context, streak


def build_warning(context: int, streak: int, last_warned: int) -> tuple[str | None, int]:
    parts = []
    new_mark = last_warned
    if context >= WARN_AT and context >= last_warned + STEP:
        k = context // 1000
        parts.append(
            f"Token Guard: this chat is at ~{k}k tokens. Every message now resends all of it, "
            f"so your next 10 messages cost ~{k * 10 / 1000:.1f}M tokens. "
            "Run /compact, or start a new session with a short summary."
        )
        new_mark = context
    if streak >= LOOP_N:
        parts.append(
            f"Token Guard: the last {streak} tool calls failed in a row. "
            "Stop and give the agent a specific hint, or fix this step by hand."
        )
    return (" ".join(parts) or None), new_mark


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    transcript = payload.get("transcript_path")
    session_id = str(payload.get("session_id") or "unknown")
    if not transcript:
        return 0

    context, streak = read_transcript(transcript)
    state_file = Path(tempfile.gettempdir()) / f"token_guard_{''.join(c for c in session_id if c.isalnum())[:40]}.json"
    last = 0
    try:
        last = int(json.loads(state_file.read_text()).get("last_warned", 0))
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    if context < last * 0.6:  # the chat was compacted — start counting again
        last = 0

    message, mark = build_warning(context, streak, last)
    try:
        state_file.write_text(json.dumps({"last_warned": mark}))
    except OSError:
        pass
    if message:
        print(json.dumps({"systemMessage": message}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
