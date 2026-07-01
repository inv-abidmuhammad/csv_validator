import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from watch import DebouncedCsvHandler


def make_event(src_path, is_directory=False):
    """Lightweight duck-typed fake of a watchdog FileSystemEvent — the
    handler only reads .src_path and .is_directory, so a real Observer
    isn't needed to exercise this logic."""
    return SimpleNamespace(src_path=src_path, is_directory=is_directory)


# ---------------------------------------------------------------------------
# Event filtering
# ---------------------------------------------------------------------------

class TestEventFiltering:
    def test_ignores_directory_events(self, tmp_path):
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=0.05)
        handler.on_created(make_event(str(tmp_path), is_directory=True))
        assert handler.pending_count() == 0

    def test_ignores_non_csv_files(self, tmp_path):
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=0.05)
        handler.on_created(make_event(str(tmp_path / "notes.txt")))
        assert handler.pending_count() == 0

    def test_schedules_timer_for_csv_file(self, tmp_path):
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=1.0)
        handler.on_created(make_event(str(tmp_path / "data.csv")))
        assert handler.pending_count() == 1
        handler.stop()  # avoid leaking a live timer into later tests

    def test_case_insensitive_csv_extension(self, tmp_path):
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=1.0)
        handler.on_created(make_event(str(tmp_path / "DATA.CSV")))
        assert handler.pending_count() == 1
        handler.stop()

    def test_on_modified_also_schedules(self, tmp_path):
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=1.0)
        handler.on_modified(make_event(str(tmp_path / "data.csv")))
        assert handler.pending_count() == 1
        handler.stop()


# ---------------------------------------------------------------------------
# Debounce behaviour
# ---------------------------------------------------------------------------

class TestDebounce:
    @patch("watch.subprocess.run")
    def test_single_event_triggers_after_quiet_period(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=0.05)

        handler.on_created(make_event(str(tmp_path / "data.csv")))
        time.sleep(0.15)

        mock_run.assert_called_once()
        assert handler.pending_count() == 0

    @patch("watch.subprocess.run")
    def test_rapid_successive_events_only_trigger_once(self, mock_run, tmp_path):
        """
        Core requirement: a file being actively written generates several
        modify events in quick succession. Only ONE validation run should
        fire once the file goes quiet — not one per event.
        """
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=0.1)

        path = str(tmp_path / "data.csv")
        for _ in range(5):
            handler.on_modified(make_event(path))
            time.sleep(0.02)  # well within the quiet period — resets the timer each time

        time.sleep(0.2)  # now let it go fully quiet

        mock_run.assert_called_once()

    @patch("watch.subprocess.run")
    def test_events_after_full_quiet_period_trigger_separately(self, mock_run, tmp_path):
        """If a file goes quiet, triggers, then gets touched again later,
        that should be treated as a new, separate run."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=0.05)

        path = str(tmp_path / "data.csv")
        handler.on_modified(make_event(path))
        time.sleep(0.15)  # first trigger fires

        handler.on_modified(make_event(path))
        time.sleep(0.15)  # second trigger fires

        assert mock_run.call_count == 2

    @patch("watch.subprocess.run")
    def test_different_files_debounced_independently(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=0.05)

        handler.on_created(make_event(str(tmp_path / "a.csv")))
        handler.on_created(make_event(str(tmp_path / "b.csv")))
        time.sleep(0.15)

        assert mock_run.call_count == 2


# ---------------------------------------------------------------------------
# Subprocess invocation
# ---------------------------------------------------------------------------

class TestTriggerCommand:
    @patch("watch.subprocess.run")
    def test_calls_main_py_in_single_mode_with_correct_args(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        handler = DebouncedCsvHandler(
            schema_name="my_schema.json", quiet_seconds=0.05, main_script="/fake/main.py"
        )

        handler.on_created(make_event(str(tmp_path / "customers.csv")))
        time.sleep(0.15)

        called_cmd = mock_run.call_args[0][0]
        assert called_cmd == [
            sys.executable, "/fake/main.py",
            "--file", "customers.csv",
            "--schema", "my_schema.json"
        ]

    @patch("watch.subprocess.run")
    def test_logs_error_on_nonzero_exit_code(self, mock_run, tmp_path, caplog):
        mock_run.return_value = MagicMock(returncode=1, stderr="something broke")
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=0.05)

        with caplog.at_level("ERROR"):
            handler.on_created(make_event(str(tmp_path / "data.csv")))
            time.sleep(0.15)

        assert any("exited with code 1" in record.message for record in caplog.records)

    @patch("watch.subprocess.run")
    def test_logs_success_on_zero_exit_code(self, mock_run, tmp_path, caplog):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=0.05)

        with caplog.at_level("INFO"):
            handler.on_created(make_event(str(tmp_path / "data.csv")))
            time.sleep(0.15)

        assert any("completed successfully" in record.message for record in caplog.records)

    @patch("watch.subprocess.run", side_effect=OSError("executable not found"))
    def test_logs_error_when_subprocess_raises(self, mock_run, tmp_path, caplog):
        """A completely broken subprocess call (e.g. bad path) must not
        crash the watcher process — it should just log and keep watching."""
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=0.05)

        with caplog.at_level("ERROR"):
            handler.on_created(make_event(str(tmp_path / "data.csv")))
            time.sleep(0.15)

        assert any("Failed to trigger validation" in record.message for record in caplog.records)
        # pending_count should still be cleaned up even though the trigger failed
        assert handler.pending_count() == 0


# ---------------------------------------------------------------------------
# pending_count()
# ---------------------------------------------------------------------------

class TestPendingCount:
    def test_zero_when_nothing_scheduled(self):
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=1.0)
        assert handler.pending_count() == 0

    def test_counts_multiple_distinct_pending_files(self, tmp_path):
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=1.0)
        handler.on_created(make_event(str(tmp_path / "a.csv")))
        handler.on_created(make_event(str(tmp_path / "b.csv")))
        handler.on_created(make_event(str(tmp_path / "c.csv")))
        assert handler.pending_count() == 3
        handler.stop()

    @patch("watch.subprocess.run")
    def test_drops_to_zero_after_trigger_fires(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=0.05)
        handler.on_created(make_event(str(tmp_path / "data.csv")))
        assert handler.pending_count() == 1
        time.sleep(0.15)
        assert handler.pending_count() == 0


# ---------------------------------------------------------------------------
# stop()
# ---------------------------------------------------------------------------

class TestStop:
    @patch("watch.subprocess.run")
    def test_stop_cancels_pending_timers_without_triggering(self, mock_run, tmp_path):
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=0.05)
        handler.on_created(make_event(str(tmp_path / "data.csv")))
        handler.stop()

        time.sleep(0.15)  # would have fired by now if not cancelled

        mock_run.assert_not_called()

    def test_stop_clears_pending_count(self, tmp_path):
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=1.0)
        handler.on_created(make_event(str(tmp_path / "data.csv")))
        handler.on_created(make_event(str(tmp_path / "other.csv")))
        assert handler.pending_count() == 2

        handler.stop()

        assert handler.pending_count() == 0

    def test_stop_safe_to_call_with_nothing_pending(self):
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=1.0)
        handler.stop()  # should not raise
        assert handler.pending_count() == 0

    def test_stop_safe_to_call_multiple_times(self, tmp_path):
        handler = DebouncedCsvHandler(schema_name="schema.json", quiet_seconds=1.0)
        handler.on_created(make_event(str(tmp_path / "data.csv")))
        handler.stop()
        handler.stop()  # should not raise
        assert handler.pending_count() == 0