"""Import your real Claude Code logs (metadata only).

Usage:
    python scripts/import_claude_code.py                 # reads ~/.claude/projects
    python scripts/import_claude_code.py --path D:\\logs --user gunesh
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal, init_db  # noqa: E402
from app.main import _save_sessions  # noqa: E402
from app.parser import parse_claude_code  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--path", default=str(Path.home() / ".claude" / "projects"), help="folder with .jsonl logs")
    ap.add_argument("--user", default="me", help="label for whose usage this is")
    args = ap.parse_args()

    root = Path(args.path).expanduser()
    files = sorted(root.rglob("*.jsonl")) if root.is_dir() else ([root] if root.is_file() else [])
    if not files:
        print(f"No .jsonl logs found at {root}. Have you used Claude Code on this machine?")
        return 1

    init_db()
    new = replaced = turns = bad = 0
    with SessionLocal() as db:
        for f in files:
            with open(f, encoding="utf-8", errors="replace") as fh:
                sessions, report = parse_claude_code(fh, user=args.user.strip().lower())
            n, r = _save_sessions(db, sessions)
            new, replaced, turns, bad = new + n, replaced + r, turns + report.turns, bad + report.bad_lines
    print(f"Read {len(files)} files: {new} new sessions, {replaced} updated, {turns} turns, {bad} unreadable lines.")
    print("Only token counts, model names, tool names and hashed file paths were stored. No prompt text.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
