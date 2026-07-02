"""Create and seed the SQLite database for the lab.

Running this script is idempotent: it drops and recreates every table,
so the database is always reproducible from scratch.
"""

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "lab.db"

SCHEMA_SQL = """
DROP TABLE IF EXISTS enrollments;
DROP TABLE IF EXISTS courses;
DROP TABLE IF EXISTS students;

CREATE TABLE students (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT NOT NULL,
    cohort TEXT NOT NULL,
    score  REAL
);

CREATE TABLE courses (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    code    TEXT NOT NULL UNIQUE,
    title   TEXT NOT NULL,
    credits INTEGER NOT NULL
);

CREATE TABLE enrollments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    course_id  INTEGER NOT NULL REFERENCES courses(id),
    grade      REAL
);
"""

SEED_SQL = """
INSERT INTO students (name, cohort, score) VALUES
    ('Alice Nguyen', 'A1', 8.5),
    ('Binh Tran',    'A1', 7.2),
    ('Chi Le',       'A2', 9.1),
    ('Dung Pham',    'A2', 6.8),
    ('En Vo',        'A1', 8.9),
    ('Phuc Hoang',   'A2', 7.5);

INSERT INTO courses (code, title, credits) VALUES
    ('CS101', 'Intro to Programming', 3),
    ('CS201', 'Data Structures',      4),
    ('AI301', 'Machine Learning',     4);

INSERT INTO enrollments (student_id, course_id, grade) VALUES
    (1, 1, 9.0),
    (1, 3, 8.0),
    (2, 1, 7.5),
    (3, 2, 9.5),
    (3, 3, 8.8),
    (4, 1, 6.0),
    (5, 2, 9.2),
    (6, 3, 7.0);
"""


def create_database(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.executescript(SEED_SQL)
        conn.commit()
    finally:
        conn.close()
    return db_path


if __name__ == "__main__":
    path = create_database()
    print(f"Database created and seeded at {path}")
