"""Seed SIMULATED demo data (idempotent).  Usage: python scripts/seed.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal, init_db  # noqa: E402
from app.simulate import seed_demo_data  # noqa: E402


def main() -> None:
    init_db()
    with SessionLocal() as db:
        result = seed_demo_data(db)
    print(f"Seeded simulated data: {result['sessions']} sessions, {result['turns']} turns "
          f"(removed {result['removed']} old simulated sessions).")


if __name__ == "__main__":
    main()
