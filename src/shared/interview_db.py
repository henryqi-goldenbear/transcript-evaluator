"""SQLite persistence for structured interview cases."""

from __future__ import annotations

import sqlite3
import re
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path("data") / "interviews.sqlite"


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS interviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interview_name TEXT NOT NULL UNIQUE,
    source_path TEXT,
    json_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interview_id INTEGER NOT NULL,
    parent_question_id INTEGER,
    case_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    question_type TEXT NOT NULL DEFAULT 'main',
    question_text TEXT NOT NULL,
    turn_type TEXT,
    rubric_type TEXT,
    probe_type TEXT,
    classification_source TEXT,
    classification_reasoning TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (interview_id) REFERENCES interviews(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_question_id) REFERENCES questions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    response_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    dimension TEXT NOT NULL,
    rating TEXT,
    score_value REAL,
    reasoning TEXT,
    model TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interview_id INTEGER,
    question_id INTEGER,
    file_name TEXT NOT NULL DEFAULT '',
    note_source TEXT NOT NULL DEFAULT 'general',
    note_type TEXT NOT NULL DEFAULT 'general',
    note_category TEXT NOT NULL DEFAULT 'general',
    note_text TEXT NOT NULL,
    note_file TEXT,
    source_file TEXT,
    note_time TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (interview_id) REFERENCES interviews(id) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_questions_interview ON questions(interview_id);
CREATE INDEX IF NOT EXISTS idx_questions_parent ON questions(parent_question_id);
CREATE INDEX IF NOT EXISTS idx_responses_question ON responses(question_id);
CREATE INDEX IF NOT EXISTS idx_scores_question ON scores(question_id);
CREATE INDEX IF NOT EXISTS idx_notes_interview ON notes(interview_id);
CREATE INDEX IF NOT EXISTS idx_notes_question ON notes(question_id);
"""


def utc_timestamp() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def ensure_note_columns(conn: sqlite3.Connection) -> None:
    existing = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(notes)").fetchall()
    }
    columns = {
        "file_name": "TEXT NOT NULL DEFAULT ''",
        "note_source": "TEXT NOT NULL DEFAULT 'general'",
        "note_category": "TEXT NOT NULL DEFAULT 'general'",
        "note_file": "TEXT",
        "source_file": "TEXT",
        "note_time": "TEXT NOT NULL DEFAULT ''",
    }
    for column, definition in columns.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE notes ADD COLUMN {column} {definition}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notes_file ON notes(note_file)")
    conn.execute(
        """
        UPDATE notes
        SET
            file_name = COALESCE(NULLIF(file_name, ''), (
                SELECT interview_name FROM interviews WHERE interviews.id = notes.interview_id
            ), ''),
            note_source = COALESCE(NULLIF(note_source, ''), note_type, 'general'),
            note_category = COALESCE(NULLIF(note_category, ''), note_type, 'general'),
            note_file = COALESCE(NULLIF(note_file, ''), source_file),
            note_time = COALESCE(NULLIF(note_time, ''), created_at)
        """
    )


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    ensure_note_columns(conn)
    migrate_legacy_notes(conn)
    return conn


def upsert_interview(
    conn: sqlite3.Connection,
    interview_name: str,
    source_path: str,
    json_path: str,
) -> int:
    now = utc_timestamp()
    conn.execute(
        """
        INSERT INTO interviews (interview_name, source_path, json_path, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(interview_name) DO UPDATE SET
            source_path = excluded.source_path,
            json_path = excluded.json_path,
            updated_at = excluded.updated_at
        """,
        (interview_name, source_path, json_path, now, now),
    )
    row = conn.execute(
        "SELECT id FROM interviews WHERE interview_name = ?",
        (interview_name,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Failed to create interview row for {interview_name}")
    interview_id = int(row["id"])
    conn.execute("DELETE FROM questions WHERE interview_id = ?", (interview_id,))
    conn.execute("DELETE FROM notes WHERE interview_id = ? AND question_id IS NULL", (interview_id,))
    return interview_id


def insert_question(
    conn: sqlite3.Connection,
    interview_id: int,
    parent_question_id: int | None,
    case_id: int,
    position: int,
    question_type: str,
    question_text: str,
    turn_type: str,
    rubric_type: str,
    probe_type: str | None,
    classification_source: str,
    classification_reasoning: str,
) -> int:
    now = utc_timestamp()
    cursor = conn.execute(
        """
        INSERT INTO questions (
            interview_id, parent_question_id, case_id, position, question_type,
            question_text, turn_type, rubric_type, probe_type,
            classification_source, classification_reasoning, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            interview_id,
            parent_question_id,
            case_id,
            position,
            question_type,
            question_text,
            turn_type,
            rubric_type,
            probe_type,
            classification_source,
            classification_reasoning,
            now,
        ),
    )
    return int(cursor.lastrowid)


def insert_response(conn: sqlite3.Connection, question_id: int, response_text: str) -> None:
    conn.execute(
        "INSERT INTO responses (question_id, response_text, created_at) VALUES (?, ?, ?)",
        (question_id, response_text or "", utc_timestamp()),
    )


def insert_note(
    conn: sqlite3.Connection,
    interview_id: int,
    note_text: str,
    note_type: str = "structure",
    question_id: int | None = None,
    file_name: str = "",
    note_source: str | None = None,
    note_category: str | None = None,
    note_file: str | None = None,
    source_file: str | None = None,
    note_time: str | None = None,
) -> None:
    timestamp = note_time or utc_timestamp()
    conn.execute(
        """
        INSERT INTO notes (
            interview_id, question_id, file_name, note_source, note_type,
            note_category, note_text, note_file, source_file, note_time, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            interview_id,
            question_id,
            file_name,
            note_source or note_type,
            note_type,
            note_category or note_type,
            note_text,
            note_file,
            source_file,
            timestamp,
            timestamp,
        ),
    )


def upsert_note_pointer(
    conn: sqlite3.Connection,
    interview_id: int,
    file_name: str,
    note_source: str,
    note_category: str,
    note_file: str,
    note_text: str,
    source_file: str | None = None,
    question_id: int | None = None,
) -> None:
    conn.execute(
        """
        DELETE FROM notes
        WHERE interview_id = ?
          AND COALESCE(question_id, 0) = COALESCE(?, 0)
          AND note_source = ?
          AND note_category = ?
          AND COALESCE(note_file, '') = ?
        """,
        (interview_id, question_id, note_source, note_category, note_file),
    )
    insert_note(
        conn,
        interview_id,
        note_text,
        note_type=note_source,
        question_id=question_id,
        file_name=file_name,
        note_source=note_source,
        note_category=note_category,
        note_file=note_file,
        source_file=source_file,
    )


def rating_to_value(rating: str | None) -> float | None:
    if rating is None:
        return None
    ratings = {
        "very poor": 1.0,
        "poor": 2.0,
        "average": 3.0,
        "good": 4.0,
        "excellent": 5.0,
        "pass": 5.0,
        "needs review": 3.0,
        "fail": 1.0,
    }
    return ratings.get(str(rating).strip().lower())


def interview_id_for_name(conn: sqlite3.Connection, interview_name: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM interviews WHERE interview_name = ?",
        (interview_name,),
    ).fetchone()
    return int(row["id"]) if row else None


def main_question_id_for_case(
    conn: sqlite3.Connection,
    interview_id: int,
    case_id: int,
) -> int | None:
    row = conn.execute(
        """
        SELECT id FROM questions
        WHERE interview_id = ? AND case_id = ? AND question_type = 'main'
        ORDER BY position
        LIMIT 1
        """,
        (interview_id, case_id),
    ).fetchone()
    return int(row["id"]) if row else None


def replace_question_scores(
    conn: sqlite3.Connection,
    question_id: int,
    scores: list[dict[str, Any]],
    model: str,
) -> None:
    conn.execute("DELETE FROM scores WHERE question_id = ?", (question_id,))
    now = utc_timestamp()
    for score in scores:
        rating = score.get("rating")
        conn.execute(
            """
            INSERT INTO scores (question_id, dimension, rating, score_value, reasoning, model, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                question_id,
                str(score.get("dimension", "")),
                str(rating) if rating is not None else None,
                score.get("score_value", rating_to_value(str(rating)) if rating is not None else None),
                str(score.get("reasoning", "")),
                model,
                now,
            ),
        )


def delete_notes_for_question_source(conn: sqlite3.Connection, question_id: int, note_source: str) -> None:
    conn.execute(
        "DELETE FROM notes WHERE question_id = ? AND note_source = ?",
        (question_id, note_source),
    )


def delete_interview_notes_for_source(conn: sqlite3.Connection, interview_id: int, note_source: str) -> None:
    conn.execute(
        "DELETE FROM notes WHERE interview_id = ? AND note_source = ?",
        (interview_id, note_source),
    )


def delete_interview_notes_for_source_file(
    conn: sqlite3.Connection,
    interview_id: int,
    note_source: str,
    source_file: str,
) -> None:
    conn.execute(
        "DELETE FROM notes WHERE interview_id = ? AND note_source = ? AND COALESCE(source_file, '') = ?",
        (interview_id, note_source, source_file),
    )


def save_agent1_result(
    result: dict[str, Any],
    db_path: Path = DEFAULT_DB_PATH,
) -> bool:
    interview_name = str(result.get("interview_name") or "").strip()
    if not interview_name:
        return False
    try:
        case_id = int(result.get("id"))
    except (TypeError, ValueError):
        return False
    parsed = result.get("parsed")
    if not isinstance(parsed, dict):
        return False

    dimensions = ["clarity", "relevance", "specificity", "self_awareness", "overall"]
    score_rows = []
    for dimension in dimensions:
        item = parsed.get(dimension)
        if not isinstance(item, dict):
            continue
        rating = item.get("rating")
        score_rows.append(
            {
                "dimension": dimension,
                "rating": rating,
                "score_value": rating_to_value(str(rating)) if rating is not None else None,
                "reasoning": item.get("reasoning", ""),
            }
        )

    conn = connect(db_path)
    try:
        interview_id = interview_id_for_name(conn, interview_name)
        if interview_id is None:
            return False
        question_id = main_question_id_for_case(conn, interview_id, case_id)
        if question_id is None:
            return False
        replace_question_scores(conn, question_id, score_rows, str(result.get("model", "")))
        log_file = str(result.get("log_file") or "").strip()
        if log_file:
            conn.execute(
                """
                DELETE FROM notes
                WHERE interview_id = ?
                  AND note_source = 'agent1_eval'
                  AND (
                      COALESCE(note_file, '') = ''
                      OR note_category <> 'evaluation_log'
                  )
                """,
                (interview_id,),
            )
            upsert_note_pointer(
                conn,
                interview_id,
                interview_name,
                "agent1_eval",
                "evaluation_log",
                log_file,
                f"Agent 1 evaluation log: {log_file}",
                source_file=log_file,
            )
        conn.commit()
        return True
    finally:
        conn.close()


def extract_agent2_verdict(report_text: str) -> str | None:
    text = str(report_text or "").lower()
    verdict_match = re.search(r"\b(pass|needs review|fail)\b", text)
    return verdict_match.group(1) if verdict_match else None


AGENT2_AGENT0_SECTIONS = {
    "structure audit",
    "follow up audit",
    "agent 1 structuring corrections",
    "agent 1 structuring guidance",
}


AGENT2_AGENT1_SECTIONS = {
    "agent 1 bias audit",
    "corrected ratings",
    "agent 1 rating corrections",
    "agent 1 rating correction guidance",
    "other qa issues",
    "top issues",
    "next steps",
    "verdict",
}


def normalize_heading(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def section_note_source(heading: str) -> str:
    normalized = normalize_heading(heading)
    if normalized in AGENT2_AGENT0_SECTIONS:
        return "agent2_eval_agent0"
    if normalized in AGENT2_AGENT1_SECTIONS:
        return "agent2_eval_agent1"
    return "agent2_eval_agent1"


def split_note_items(section_text: str) -> list[str]:
    items: list[str] = []
    paragraph: list[str] = []
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line:
            if paragraph:
                items.append(" ".join(paragraph).strip())
                paragraph = []
            continue
        if re.match(r"^[-*]\s+", line) or re.match(r"^\d+[.)]\s+", line):
            if paragraph:
                items.append(" ".join(paragraph).strip())
                paragraph = []
            items.append(re.sub(r"^([-*]|\d+[.)])\s+", "", line).strip())
        else:
            paragraph.append(line)
    if paragraph:
        items.append(" ".join(paragraph).strip())
    return [item for item in items if item and not item.startswith("Timestamp:")]


def extract_agent2_notes(report_text: str) -> list[dict[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    current_heading = "general"
    current_lines: list[str] = []
    for raw_line in str(report_text or "").splitlines():
        heading_match = re.match(r"^\s{0,3}#{1,4}\s+(.+?)\s*$", raw_line)
        if heading_match:
            if current_lines:
                sections.append((current_heading, current_lines))
            current_heading = heading_match.group(1).strip().strip("*")
            current_lines = []
        else:
            current_lines.append(raw_line)
    if current_lines:
        sections.append((current_heading, current_lines))

    notes: list[dict[str, str]] = []
    for heading, lines in sections:
        normalized = normalize_heading(heading)
        if normalized in {"agent 2 report", "general", "error"}:
            continue
        source = section_note_source(heading)
        for item in split_note_items("\n".join(lines)):
            if item.lower().startswith(("source:", "date:", "conversation id:")):
                continue
            notes.append(
                {
                    "note_source": source,
                    "note_category": normalized or "general",
                    "note_text": item,
                }
            )
    return notes


def migrate_legacy_notes(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        DELETE FROM notes
        WHERE note_type = 'agent1_overall'
           OR (
                note_source = 'agent1_eval'
                AND (
                    COALESCE(note_file, '') = ''
                    OR note_category <> 'evaluation_log'
                )
           )
        """
    )
    legacy_reports = conn.execute(
        """
        SELECT id, interview_id, file_name, note_text, source_file, note_time
        FROM notes
        WHERE note_type = 'agent2_report' OR note_source = 'agent2_report'
        """
    ).fetchall()
    for row in legacy_reports:
        insert_note(
            conn,
            int(row["interview_id"]),
            str(row["note_text"] or ""),
            note_type="agent2_eval",
            question_id=None,
            file_name=str(row["file_name"] or ""),
            note_source="agent2_eval",
            note_category="agent2_report",
            source_file=str(row["source_file"] or ""),
            note_time=str(row["note_time"] or utc_timestamp()),
        )
        conn.execute("DELETE FROM notes WHERE id = ?", (int(row["id"]),))
    collapse_split_agent2_notes(conn)
    conn.execute(
        """
        DELETE FROM notes
        WHERE note_type = 'structure'
          AND note_text LIKE 'Stored % approved structured case(s)%'
        """
    )


def collapse_split_agent2_notes(conn: sqlite3.Connection) -> None:
    groups = conn.execute(
        """
        SELECT
            interview_id,
            COALESCE(file_name, '') AS file_name,
            COALESCE(source_file, '') AS source_file,
            COALESCE(note_time, created_at) AS note_time,
            COUNT(*) AS row_count
        FROM notes
        WHERE note_source IN ('agent2_eval_agent0', 'agent2_eval_agent1')
        GROUP BY interview_id, COALESCE(file_name, ''), COALESCE(source_file, ''), COALESCE(note_time, created_at)
        HAVING COUNT(*) > 0
        """
    ).fetchall()
    for group in groups:
        rows = conn.execute(
            """
            SELECT id, note_source, note_category, note_text, created_at
            FROM notes
            WHERE interview_id = ?
              AND COALESCE(file_name, '') = ?
              AND COALESCE(source_file, '') = ?
              AND COALESCE(note_time, created_at) = ?
              AND note_source IN ('agent2_eval_agent0', 'agent2_eval_agent1')
            ORDER BY id
            """,
            (
                int(group["interview_id"]),
                str(group["file_name"]),
                str(group["source_file"]),
                str(group["note_time"]),
            ),
        ).fetchall()
        if not rows:
            continue
        combined = ["# Agent 2 Migrated Notes", ""]
        for row in rows:
            combined.extend(
                [
                    f"## {row['note_source']} / {row['note_category']}",
                    "",
                    str(row["note_text"] or ""),
                    "",
                ]
            )
        insert_note(
            conn,
            int(group["interview_id"]),
            "\n".join(combined).strip(),
            note_type="agent2_eval",
            question_id=None,
            file_name=str(group["file_name"]),
            note_source="agent2_eval",
            note_category="agent2_report",
            source_file=str(group["source_file"]),
            note_time=str(group["note_time"]),
        )
        conn.executemany("DELETE FROM notes WHERE id = ?", [(int(row["id"]),) for row in rows])


def save_agent2_report_note(
    interview_name: str,
    report_text: str,
    source_name: str = "",
    db_path: Path = DEFAULT_DB_PATH,
    report_path: str = "",
) -> bool:
    conn = connect(db_path)
    try:
        interview_id = interview_id_for_name(conn, interview_name)
        if interview_id is None:
            return False
        note_file = report_path or source_name
        if note_file:
            delete_interview_notes_for_source_file(conn, interview_id, "agent2_eval", note_file)
        upsert_note_pointer(
            conn,
            interview_id,
            interview_name,
            "agent2_eval",
            "agent2_report",
            note_file,
            f"Agent 2 report: {note_file}",
            source_file=source_name,
        )
        verdict = extract_agent2_verdict(report_text)
        if verdict:
            cursor = conn.execute(
                """
                INSERT INTO questions (
                    interview_id, parent_question_id, case_id, position, question_type,
                    question_text, turn_type, rubric_type, probe_type,
                    classification_source, classification_reasoning, created_at
                )
                VALUES (?, NULL, 0, 0, 'agent2_report', ?, '', '', NULL, ?, ?, ?)
                """,
                (
                    interview_id,
                    f"Agent 2 final QA verdict ({source_name})",
                    "agent2",
                    "Synthetic question row for Agent 2 final report verdict.",
                    utc_timestamp(),
                ),
            )
            replace_question_scores(
                conn,
                int(cursor.lastrowid),
                [
                    {
                        "dimension": "agent2_verdict",
                        "rating": verdict,
                        "score_value": rating_to_value(verdict),
                        "reasoning": "Parsed from Agent 2 final QA report.",
                    }
                ],
                "agent2",
            )
        conn.commit()
        return True
    finally:
        conn.close()


def save_interview_cases(
    cases: list[dict[str, Any]],
    interview_name: str,
    source_path: Path,
    json_path: Path,
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    """Replace one interview's structured questions/responses in SQLite."""

    conn = connect(db_path)
    try:
        interview_id = upsert_interview(
            conn,
            interview_name,
            source_path.as_posix(),
            json_path.as_posix(),
        )

        position = 1
        for case in cases:
            case_id = int(case.get("id") or position)
            classification_source = str(case.get("classification_source", ""))
            classification_reasoning = str(case.get("classification_reasoning", ""))
            main_question_id = insert_question(
                conn,
                interview_id=interview_id,
                parent_question_id=None,
                case_id=case_id,
                position=position,
                question_type="main",
                question_text=str(case.get("question", "")),
                turn_type=str(case.get("turn_type", "")),
                rubric_type=str(case.get("rubric_type", "")),
                probe_type=None,
                classification_source=classification_source,
                classification_reasoning=classification_reasoning,
            )
            insert_response(conn, main_question_id, str(case.get("response", "")))
            position += 1

            for follow in case.get("follow_ups", []) or []:
                follow_classification_source = str(follow.get("classification_source", ""))
                follow_reasoning = str(follow.get("classification_reasoning", "Follow-up attached to parent case."))
                follow_question_id = insert_question(
                    conn,
                    interview_id=interview_id,
                    parent_question_id=main_question_id,
                    case_id=case_id,
                    position=position,
                    question_type="follow_up",
                    question_text=str(follow.get("question", "")),
                    turn_type=str(case.get("turn_type", "")),
                    rubric_type=str(case.get("rubric_type", "")),
                    probe_type=str(follow.get("probe_type", "")),
                    classification_source=follow_classification_source,
                    classification_reasoning=follow_reasoning,
                )
                insert_response(conn, follow_question_id, str(follow.get("response", "")))
                position += 1

        conn.commit()
        return interview_id
    finally:
        conn.close()
