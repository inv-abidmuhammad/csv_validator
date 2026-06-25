import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from validator.tracker import (
    FAILED,
    SUCCESS,
    get_file_status,
    get_report_path,
    initialize_db,
    record_result,
)


class TestTracker:
    def test_initialize_db_creates_table(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        conn = sqlite3.connect(db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        assert ("processed_files",) in tables

    def test_initialize_db_is_idempotent(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        initialize_db(db_path)  # second call should not raise

    def test_get_file_status_returns_none_for_unknown(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        assert get_file_status(db_path, "nonexistent_hash") is None

    def test_record_and_retrieve_success_status(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        record_result(db_path, "abc123", "file.csv", SUCCESS, "/reports/file.json")
        assert get_file_status(db_path, "abc123") == SUCCESS

    def test_record_and_retrieve_failed_status(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        record_result(db_path, "def456", "file2.csv", FAILED, "/reports/file2.json")
        assert get_file_status(db_path, "def456") == FAILED

    def test_get_report_path_returns_none_for_unknown(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        assert get_report_path(db_path, "nonexistent") is None

    def test_get_report_path_returns_correct_path(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        record_result(db_path, "hash1", "file.csv", SUCCESS, "/reports/file.json")
        assert get_report_path(db_path, "hash1") == "/reports/file.json"

    def test_record_result_upserts_on_duplicate_hash(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        record_result(db_path, "hash1", "file.csv", SUCCESS, "/a.json")
        record_result(db_path, "hash1", "file.csv", FAILED, "/b.json")
        assert get_file_status(db_path, "hash1") == FAILED
        assert get_report_path(db_path, "hash1") == "/b.json"

    def test_record_result_handles_none_report_path(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        record_result(db_path, "hash2", "file.csv", SUCCESS, None)
        assert get_file_status(db_path, "hash2") == SUCCESS
        assert get_report_path(db_path, "hash2") is None