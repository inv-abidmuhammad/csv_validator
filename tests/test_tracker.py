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

    def test_initialize_db_uses_combined_hash_column(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        conn = sqlite3.connect(db_path)
        columns = [
            row[1]
            for row in conn.execute("PRAGMA table_info(processed_files)").fetchall()
        ]
        conn.close()
        assert "combined_hash" in columns
        assert "file_hash" not in columns

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
        record_result(db_path, "combined_abc", "file.csv", SUCCESS, "/reports/file.json")
        assert get_file_status(db_path, "combined_abc") == SUCCESS

    def test_record_and_retrieve_failed_status(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        record_result(db_path, "combined_def", "file2.csv", FAILED, "/reports/file2.json")
        assert get_file_status(db_path, "combined_def") == FAILED

    def test_get_report_path_returns_none_for_unknown(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        assert get_report_path(db_path, "nonexistent") is None

    def test_get_report_path_returns_correct_path(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        record_result(db_path, "combined_hash1", "file.csv", SUCCESS, "/reports/file.json")
        assert get_report_path(db_path, "combined_hash1") == "/reports/file.json"

    def test_same_file_different_schema_both_stored(self, tmp_path):
        """Same file processed with two schemas should produce two independent DB rows."""
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        record_result(db_path, "combined_schema1", "file.csv", FAILED, "/r1.json")
        record_result(db_path, "combined_schema2", "file.csv", SUCCESS, "/r2.json")
        assert get_file_status(db_path, "combined_schema1") == FAILED
        assert get_file_status(db_path, "combined_schema2") == SUCCESS

    def test_same_file_updated_schema_not_skipped(self, tmp_path):
        """After schema changes, the old combined hash should not match the new one."""
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        record_result(db_path, "old_combined", "file.csv", FAILED, "/old.json")
        # New combined hash (schema changed) should return None — not skipped
        assert get_file_status(db_path, "new_combined") is None

    def test_record_result_upserts_on_duplicate_combined_hash(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        record_result(db_path, "combined_hash1", "file.csv", SUCCESS, "/a.json")
        record_result(db_path, "combined_hash1", "file.csv", FAILED, "/b.json")
        assert get_file_status(db_path, "combined_hash1") == FAILED
        assert get_report_path(db_path, "combined_hash1") == "/b.json"

    def test_record_result_handles_none_report_path(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        record_result(db_path, "combined_hash2", "file.csv", SUCCESS, None)
        assert get_file_status(db_path, "combined_hash2") == SUCCESS
        assert get_report_path(db_path, "combined_hash2") is None