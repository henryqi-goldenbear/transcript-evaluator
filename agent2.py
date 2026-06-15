"""Compatibility launcher for Agent 2.

Prefer running `python -m src.agent2.agent2`.
"""

from src.agent2.agent2 import main


if __name__ == "__main__":
    raise SystemExit(main())
