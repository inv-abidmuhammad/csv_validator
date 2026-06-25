import sqlite3
from datetime import datetime

SUCCESS = "SUCCESS"
FAILED = "FAILED"


def initialize_db(db_path):
    conn = sqlite3.connect(db_path)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS processed_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_hash TEXT UNIQUE NOT NULL,
            filename TEXT NOT NULL,
            status TEXT NOT NULL,
            processed_at TIMESTAMP NOT NULL,
            report_path TEXT
        )
    """)

    conn.commit()
    conn.close()


def get_file_status(db_path, file_hash):
    conn = sqlite3.connect(db_path)

    cursor = conn.execute(
        """
        SELECT status
        FROM processed_files
        WHERE file_hash = ?
        """,
        (file_hash,)
    )

    row = cursor.fetchone()

    conn.close()

    if row:
        return row[0]

    return None


def get_report_path(db_path, file_hash):
    conn = sqlite3.connect(db_path)

    cursor = conn.execute(
        """
        SELECT report_path
        FROM processed_files
        WHERE file_hash = ?
        """,
        (file_hash,)
    )

    row = cursor.fetchone()

    conn.close()

    if row:
        return row[0]

    return None

    
def record_result(
    db_path,
    file_hash,
    filename,
    status,
    report_path
):
    conn = sqlite3.connect(db_path)
    report_path = str(report_path) if report_path else None

    conn.execute(
        """
        INSERT OR REPLACE INTO processed_files (
            file_hash,
            filename,
            status,
            processed_at,
            report_path
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            file_hash,
            filename,
            status,
            datetime.now().isoformat(),
            report_path
        )
    )

    conn.commit()
    conn.close()