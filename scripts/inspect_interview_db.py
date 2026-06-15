"""Inspect the transcript evaluator SQLite database."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.shared.interview_db import connect


def table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [str(row["name"]) for row in rows]


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def print_counts(conn: sqlite3.Connection) -> None:
    for table in table_names(conn):
        count = conn.execute(f"SELECT COUNT(*) FROM {quote_identifier(table)}").fetchone()[0]
        print(f"{table}: {count}")


def print_table(conn: sqlite3.Connection, table: str, limit: int) -> None:
    available = set(table_names(conn))
    if table not in available:
        raise ValueError(f"Unknown table: {table}. Available tables: {', '.join(sorted(available))}")

    quoted = quote_identifier(table)
    columns = [str(row["name"]) for row in conn.execute(f"PRAGMA table_info({quoted})").fetchall()]
    rows = conn.execute(f"SELECT * FROM {quoted} ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    print(f"\n## {table}")
    print(f"columns: {', '.join(columns)}")
    if not rows:
        print("(empty)")
        return

    for row in rows:
        print("-" * 80)
        for column in columns:
            value = row[column]
            text = "" if value is None else str(value)
            if len(text) > 500:
                text = f"{text[:500]} [...truncated {len(text) - 500} chars]"
            print(f"{column}: {text}")


def print_all_tables(conn: sqlite3.Connection, limit: int) -> None:
    for table in table_names(conn):
        print_table(conn, table, limit)


def print_recent(conn: sqlite3.Connection, limit: int) -> None:
    rows = conn.execute(
        """
        SELECT
            i.interview_name,
            q.case_id,
            q.question_type,
            q.question_text,
            r.response_text
        FROM questions q
        JOIN interviews i ON i.id = q.interview_id
        LEFT JOIN responses r ON r.question_id = q.id
        ORDER BY i.updated_at DESC, q.position ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    for row in rows:
        print("-" * 80)
        print(f"interview: {row['interview_name']}")
        print(f"case: {row['case_id']} ({row['question_type']})")
        print(f"question: {row['question_text']}")
        print(f"response: {row['response_text'] or ''}")


def print_scores(conn: sqlite3.Connection, limit: int) -> None:
    rows = conn.execute(
        """
        SELECT
            i.interview_name,
            q.case_id,
            s.dimension,
            s.rating,
            s.score_value,
            s.reasoning,
            s.model
        FROM scores s
        JOIN questions q ON q.id = s.question_id
        JOIN interviews i ON i.id = q.interview_id
        ORDER BY s.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    for row in rows:
        print("-" * 80)
        print(f"interview: {row['interview_name']} case: {row['case_id']}")
        print(f"{row['dimension']}: {row['rating']} ({row['score_value']}) model={row['model']}")
        print(f"reasoning: {row['reasoning'] or ''}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect interview SQLite data.")
    parser.add_argument("--db", default="data/interviews.sqlite", help="SQLite DB path.")
    parser.add_argument("--limit", type=int, default=10, help="Rows to show.")
    parser.add_argument("--scores", action="store_true", help="Show recent scores instead of Q/A rows.")
    parser.add_argument("--all-tables", action="store_true", help="Show rows from every table.")
    parser.add_argument("--table", help="Show rows from one table.")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = connect(db_path)
    print(f"DB: {db_path}")
    print_counts(conn)
    if args.all_tables:
        print_all_tables(conn, args.limit)
    elif args.table:
        print_table(conn, args.table, args.limit)
    elif args.scores:
        print()
        print_scores(conn, args.limit)
    else:
        print()
        print_recent(conn, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
