"""Weekly waste report (Markdown). Schedule it, then paste/send the output.

Usage:
    python scripts/weekly_report.py                 # last 7 days -> prints Markdown
    python scripts/weekly_report.py --days 14 --out report.md --source real
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import analytics  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402


def tok(n: float) -> str:
    for size, unit in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(n) >= size:
            return f"{n / size:.1f}{unit}"
    return f"{n:.0f}"


def build_report(days: int = 7, source: str = "all", now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    since = now - timedelta(days=days)
    init_db()
    with SessionLocal() as db:
        stats = [s for s in analytics.load_stats(db, source=source) if s.session.started_at >= since]
        if not stats:
            return f"# LLM Token Auditor report\n\nNo sessions in the last {days} days.\n"
        ov = analytics.overview(stats)
        users = analytics.by_user(stats)
        fc = analytics.forecast(analytics.load_stats(db, source=source), now=now)

    lines = [
        f"# LLM Token Auditor report: {since:%d %b} to {now:%d %b %Y}",
        "",
    ]
    if ov["has_simulated"]:
        lines += ["> **Simulated data** (demo team, not a real company).", ""]
    lines += [
        f"- **Usage:** {tok(ov['total_tokens'])} tokens across {ov['sessions']} sessions by {ov['users']} developers (est. ${ov['total_cost']:,.2f})",
        f"- **Avoidable:** {tok(ov['waste_tokens'])} tokens ({ov['waste_token_pct']}%), est. ${ov['waste_cost']:,.2f} ({ov['waste_cost_pct']}% of spend)",
    ]
    if fc["budget_hit_date"]:
        tail = (
            f"with fixes: {fc['budget_hit_date_with_fixes']}" if fc["budget_hit_date_with_fixes"] else "with fixes: stays under budget"
        )
        lines.append(f"- **Budget alert:** at this pace the monthly token budget is reached on {fc['budget_hit_date']} ({tail})")
    else:
        lines.append("- **Budget:** on track to stay under the monthly token budget")
    lines += ["", "## Top 3 fixes", ""]
    for i, r in enumerate(ov["by_rule"][:3], 1):
        lines.append(f"{i}. **{r['title']}** ({r['sessions']} sessions, est. ${r['cost_wasted']:,.2f} avoidable). {r['fix']}")
    lines += ["", "## By developer", "", "| Developer | Tokens | Avoidable | Biggest issue |", "|---|---|---|---|"]
    for u in users:
        lines.append(f"| {u['user']} | {tok(u['tokens'])} | {u['waste_token_pct']}% | {u['top_issue']} |")
    lines += ["", "_Waste figures are conservative rule-based estimates. Only usage metadata is analysed, never prompt text._", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--source", choices=["all", "real", "simulated"], default="all")
    ap.add_argument("--out", help="write to this file instead of printing")
    args = ap.parse_args()
    report = build_report(days=args.days, source=args.source)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
