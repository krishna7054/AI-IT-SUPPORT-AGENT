from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import init_db
from backend.database import reset_demo_data


def main() -> None:
    try:
        reset_demo_data()
    except FileNotFoundError:
        init_db()
    print("Reset demo database to the seeded users")


if __name__ == "__main__":
    main()
