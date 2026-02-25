import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bank_poc.db"
SCHEMA_PATH = BASE_DIR / "db_schema.sql"


def main() -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(schema_sql)
        conn.commit()

    print(f"SQLite DB initialized: {DB_PATH}")


if __name__ == "__main__":
    main()
