"""
Tests for main.py CLI behaviour.

Runs main.py as a subprocess so argparse and sys.exit behave exactly
as they would in production.
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
MAIN = ROOT / "main.py"


def make_project(tmp_path, csv_content=None, schema_content=None, report_formats=None, email_config=None):
    """Scaffold the minimum folder structure main.py expects."""
    (tmp_path / "input").mkdir()
    (tmp_path / "schemas").mkdir()
    (tmp_path / "reports").mkdir()
    (tmp_path / "config").mkdir()

    config = {
        "input_folder": str(tmp_path / "input"),
        "schema_folder": str(tmp_path / "schemas"),
        "report_folder": str(tmp_path / "reports"),
        "database_path": str(tmp_path / "tracker.db"),
    }
    if report_formats is not None:
        config["report_formats"] = report_formats
    if email_config is not None:
        config["email"] = email_config

    (tmp_path / "config" / "config.json").write_text(json.dumps(config))

    if csv_content:
        (tmp_path / "input" / "data.csv").write_text(csv_content)

    if schema_content:
        (tmp_path / "schemas" / "schema.json").write_text(json.dumps(schema_content))

    return config


def run_main(tmp_path, extra_args=None, stdin=None):
    """Run main.py from tmp_path and return CompletedProcess."""
    cmd = [sys.executable, str(MAIN)] + (extra_args or [])
    return subprocess.run(
        cmd,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        input=stdin,
    )


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------

class TestArgParsing:
    def test_file_without_schema_errors(self, tmp_path):
        make_project(tmp_path)
        result = run_main(tmp_path, ["--file", "data.csv"])
        assert result.returncode != 0
        assert "--file and --schema must be provided together" in result.stderr

    def test_schema_without_file_runs_batch_mode(self, tmp_path):
        """--schema alone is valid — it runs batch mode without the interactive prompt."""
        make_project(tmp_path)
        result = run_main(tmp_path, ["--schema", "schema.json"])
        # No CSV files exist, so it exits with a warning — but it's not an arg error
        assert "--file and --schema must be provided together" not in result.stderr


# ---------------------------------------------------------------------------
# Single mode
# ---------------------------------------------------------------------------

class TestSingleMode:
    def test_exits_0_on_valid_file_and_schema(self, tmp_path):
        make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
        )
        result = run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        assert result.returncode == 0

    def test_logs_independent_run_tag(self, tmp_path):
        make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
        )
        result = run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        assert "[INDEPENDENT RUN]" in result.stderr

    def test_generates_report(self, tmp_path):
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
        )
        run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        reports = list(Path(config["report_folder"]).glob("*.json"))
        assert len(reports) == 1

    def test_report_contains_summary_stats(self, tmp_path):
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\nBob,not_a_number\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
        )
        run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        report_path = next(Path(config["report_folder"]).glob("*.json"))
        report = json.loads(report_path.read_text())
        assert report["summary"]["rows_processed"] == 2
        assert report["summary"]["rows_passed"] == 1
        assert report["summary"]["rows_failed"] == 1

    def test_records_result_in_db(self, tmp_path):
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
        )
        run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        conn = sqlite3.connect(config["database_path"])
        rows = conn.execute("SELECT * FROM processed_files").fetchall()
        conn.close()
        assert len(rows) == 1

    def test_missing_file_exits_with_error(self, tmp_path):
        make_project(
            tmp_path,
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
            }},
        )
        result = run_main(tmp_path, ["--file", "missing.csv", "--schema", "schema.json"])
        assert result.returncode != 0
        assert "not found in input folder" in result.stderr

    def test_missing_schema_exits_with_error(self, tmp_path):
        make_project(
            tmp_path,
            csv_content="name\nAlice\n",
        )
        result = run_main(tmp_path, ["--file", "data.csv", "--schema", "missing.json"])
        assert result.returncode != 0
        assert "not found in schema folder" in result.stderr

    def test_runs_regardless_of_prior_db_entry(self, tmp_path):
        """Core requirement: single mode always runs, even if already in DB."""
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
        )
        run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        reports = list(Path(config["report_folder"]).glob("*.json"))
        assert len(reports) == 2

    def test_failed_validation_recorded_as_failed(self, tmp_path):
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,not_a_number\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
        )
        run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        conn = sqlite3.connect(config["database_path"])
        row = conn.execute("SELECT status FROM processed_files").fetchone()
        conn.close()
        assert row[0] == "FAILED"

    def test_does_not_log_already_processed_message(self, tmp_path):
        """Single mode should never log that a file was already processed."""
        make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
        )
        run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        result = run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        assert "already processed" not in result.stderr.lower()

    def test_cross_field_rule_violation_recorded_as_failed(self, tmp_path):
        """End-to-end: a schema with cross_field_rules correctly fails a violating row."""
        config = make_project(
            tmp_path,
            csv_content="start_date,end_date\n10,5\n",  # end before start — invalid
            schema_content={
                "columns": {
                    "start_date": {"type": "int", "required": True},
                    "end_date": {"type": "int", "required": True},
                },
                "cross_field_rules": [
                    {"type": "greater_than", "field": "end_date", "than": "start_date"}
                ],
            },
        )
        run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        conn = sqlite3.connect(config["database_path"])
        row = conn.execute("SELECT status FROM processed_files").fetchone()
        conn.close()
        assert row[0] == "FAILED"


# ---------------------------------------------------------------------------
# Batch mode unaffected
# ---------------------------------------------------------------------------

class TestBatchModeUnaffected:
    def test_batch_mode_still_skips_processed_files(self, tmp_path):
        """Batch mode DB-skip behaviour should be unchanged."""
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
        )
        # First batch run — processes the file
        run_main(tmp_path, stdin="1\n")
        # Second batch run — should skip it
        result = run_main(tmp_path, stdin="1\n")
        assert "already processed" in result.stderr.lower()

    def test_batch_and_single_mode_are_independent(self, tmp_path):
        """A file processed in batch mode is still processed in single mode."""
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
        )
        # Batch run first
        run_main(tmp_path, stdin="1\n")
        # Single mode should still run — not skip
        result = run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        assert result.returncode == 0
        assert "already processed" not in result.stderr.lower()
        assert "[INDEPENDENT RUN]" in result.stderr


# ---------------------------------------------------------------------------
# Batch mode with --schema flag (cron-friendly)
# ---------------------------------------------------------------------------

class TestBatchModeSchemaFlag:
    def test_batch_schema_flag_skips_prompt(self, tmp_path):
        """--schema in batch mode should process without any interactive input."""
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
        )
        result = run_main(tmp_path, ["--schema", "schema.json"])
        assert result.returncode == 0

    def test_batch_schema_flag_processes_files(self, tmp_path):
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
        )
        run_main(tmp_path, ["--schema", "schema.json"])
        conn = sqlite3.connect(config["database_path"])
        rows = conn.execute("SELECT * FROM processed_files").fetchall()
        conn.close()
        assert len(rows) == 1

    def test_batch_schema_flag_missing_schema_errors(self, tmp_path):
        make_project(
            tmp_path,
            csv_content="name\nAlice\n",
            schema_content={"columns": {"name": {"type": "string", "required": True}}},
        )
        result = run_main(tmp_path, ["--schema", "missing.json"])
        assert result.returncode != 0
        assert "not found in schema folder" in result.stderr

    def test_batch_schema_flag_still_skips_processed_files(self, tmp_path):
        """DB skip behaviour should still apply in cron/batch mode."""
        make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
        )
        run_main(tmp_path, ["--schema", "schema.json"])
        result = run_main(tmp_path, ["--schema", "schema.json"])
        assert "already processed" in result.stderr.lower()

    def test_batch_schema_flag_does_not_trigger_single_mode(self, tmp_path):
        """--schema alone should NOT be treated as single mode (no --file)."""
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
        )
        result = run_main(tmp_path, ["--schema", "schema.json"])
        assert "[INDEPENDENT RUN]" not in result.stderr


# ---------------------------------------------------------------------------
# CSV / HTML report formats (config-driven)
# ---------------------------------------------------------------------------

class TestReportFormats:
    def test_no_report_formats_configured_only_json(self, tmp_path):
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
        )
        run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        report_folder = Path(config["report_folder"])
        assert len(list(report_folder.glob("*.json"))) == 1
        assert len(list(report_folder.glob("*.csv"))) == 0
        assert len(list(report_folder.glob("*.html"))) == 0

    def test_report_formats_csv_generates_csv_file(self, tmp_path):
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
            report_formats=["csv"],
        )
        run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        report_folder = Path(config["report_folder"])
        assert len(list(report_folder.glob("*.csv"))) == 1

    def test_report_formats_html_generates_html_file(self, tmp_path):
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
            report_formats=["html"],
        )
        run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        report_folder = Path(config["report_folder"])
        assert len(list(report_folder.glob("*.html"))) == 1

    def test_report_formats_both_generates_all_three(self, tmp_path):
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
            report_formats=["csv", "html"],
        )
        run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        report_folder = Path(config["report_folder"])
        assert len(list(report_folder.glob("*.json"))) == 1
        assert len(list(report_folder.glob("*.csv"))) == 1
        assert len(list(report_folder.glob("*.html"))) == 1

    def test_works_in_batch_mode_too(self, tmp_path):
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
            report_formats=["csv"],
        )
        run_main(tmp_path, ["--schema", "schema.json"])
        report_folder = Path(config["report_folder"])
        assert len(list(report_folder.glob("*.csv"))) == 1


# ---------------------------------------------------------------------------
# Email delivery (config-driven, graceful failure)
# ---------------------------------------------------------------------------

class TestEmailDelivery:
    def test_no_email_config_does_not_attempt_send(self, tmp_path):
        """Without an 'email' section, nothing related to email should be logged."""
        make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
        )
        result = run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        assert result.returncode == 0
        assert "report emailed" not in result.stderr.lower()
        assert "failed to send report email" not in result.stderr.lower()

    def test_email_disabled_flag_does_not_attempt_send(self, tmp_path):
        make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
            email_config={"enabled": False, "host": "smtp.example.com", "port": 587,
                          "from_address": "bot@example.com", "to_address": "team@example.com"},
        )
        result = run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        assert result.returncode == 0
        assert "report emailed" not in result.stderr.lower()
        assert "failed to send report email" not in result.stderr.lower()

    def test_email_failure_does_not_crash_run(self, tmp_path):
        """
        Core requirement: an unreachable/misconfigured SMTP server must not
        crash validation. The report should still be generated and the run
        should still exit 0, with the failure only logged.
        """
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
            # Deliberately unreachable host/port so the send fails fast
            email_config={"enabled": True, "host": "127.0.0.1", "port": 1,
                          "from_address": "bot@example.com", "to_address": "team@example.com"},
        )
        result = run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])

        # The run itself must still succeed
        assert result.returncode == 0

        # The report must still be generated despite the email failure
        reports = list(Path(config["report_folder"]).glob("*.json"))
        assert len(reports) == 1

        # The failure should be logged, not silently swallowed
        assert "failed to send report email" in result.stderr.lower()

    def test_email_failure_does_not_prevent_db_record(self, tmp_path):
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
            email_config={"enabled": True, "host": "127.0.0.1", "port": 1,
                          "from_address": "bot@example.com", "to_address": "team@example.com"},
        )
        run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        conn = sqlite3.connect(config["database_path"])
        rows = conn.execute("SELECT * FROM processed_files").fetchall()
        conn.close()
        assert len(rows) == 1

    def test_email_works_in_batch_mode_too(self, tmp_path):
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
            email_config={"enabled": True, "host": "127.0.0.1", "port": 1,
                          "from_address": "bot@example.com", "to_address": "team@example.com"},
        )
        result = run_main(tmp_path, ["--schema", "schema.json"])
        assert result.returncode == 0
        assert "failed to send batch report email" in result.stderr.lower()

    def test_batch_mode_sends_only_one_email_attempt_for_multiple_files(self, tmp_path):
        """
        Core requirement: N files processed in batch mode should result in
        exactly ONE email attempt, not N. We verify this indirectly by
        counting log occurrences of the (failing, since host is unreachable)
        send attempt — it must appear exactly once regardless of file count.
        """
        (tmp_path / "input").mkdir()
        (tmp_path / "schemas").mkdir()
        (tmp_path / "reports").mkdir()
        (tmp_path / "config").mkdir()

        config = {
            "input_folder": str(tmp_path / "input"),
            "schema_folder": str(tmp_path / "schemas"),
            "report_folder": str(tmp_path / "reports"),
            "database_path": str(tmp_path / "tracker.db"),
            "email": {"enabled": True, "host": "127.0.0.1", "port": 1,
                      "from_address": "bot@example.com", "to_address": "team@example.com"},
        }
        (tmp_path / "config" / "config.json").write_text(json.dumps(config))

        # Three separate CSV files in the input folder
        for i in range(3):
            (tmp_path / "input" / f"file{i}.csv").write_text("name,age\nAlice,30\n")

        (tmp_path / "schemas" / "schema.json").write_text(json.dumps({
            "columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }
        }))

        result = run_main(tmp_path, ["--schema", "schema.json"])

        assert result.returncode == 0
        # Exactly one attempt logged, not three
        assert result.stderr.lower().count("failed to send batch report email") == 1

    def test_batch_mode_generates_csv_reports_for_email_even_without_report_formats_config(self, tmp_path):
        """CSV reports should be written automatically when email is enabled,
        even if report_formats doesn't explicitly request 'csv'."""
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
            email_config={"enabled": True, "host": "127.0.0.1", "port": 1,
                          "from_address": "bot@example.com", "to_address": "team@example.com"},
        )
        run_main(tmp_path, ["--schema", "schema.json"])
        csv_reports = list(Path(config["report_folder"]).glob("*.csv"))
        assert len(csv_reports) == 1

    def test_single_mode_generates_csv_report_for_email(self, tmp_path):
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
            email_config={"enabled": True, "host": "127.0.0.1", "port": 1,
                          "from_address": "bot@example.com", "to_address": "team@example.com"},
        )
        run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        csv_reports = list(Path(config["report_folder"]).glob("*.csv"))
        assert len(csv_reports) == 1

    def test_no_csv_report_written_when_email_disabled_and_not_requested(self, tmp_path):
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
        )
        run_main(tmp_path, ["--file", "data.csv", "--schema", "schema.json"])
        csv_reports = list(Path(config["report_folder"]).glob("*.csv"))
        assert len(csv_reports) == 0


# ---------------------------------------------------------------------------
# Progress indicator (non-interactive under subprocess — should be silent)
# ---------------------------------------------------------------------------

class TestProgressIndicator:
    def test_no_carriage_return_garbage_in_non_interactive_output(self, tmp_path):
        """
        subprocess.run captures output via a pipe, never a real TTY, so the
        progress bar must not render at all here — matching cron behavior.
        A leaked '\\r' would corrupt a redirected log file.
        """
        (tmp_path / "input").mkdir()
        (tmp_path / "schemas").mkdir()
        (tmp_path / "reports").mkdir()
        (tmp_path / "config").mkdir()

        config = {
            "input_folder": str(tmp_path / "input"),
            "schema_folder": str(tmp_path / "schemas"),
            "report_folder": str(tmp_path / "reports"),
            "database_path": str(tmp_path / "tracker.db"),
        }
        (tmp_path / "config" / "config.json").write_text(json.dumps(config))

        for i in range(5):
            (tmp_path / "input" / f"file{i}.csv").write_text("name,age\nAlice,30\n")

        (tmp_path / "schemas" / "schema.json").write_text(json.dumps({
            "columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }
        }))

        result = run_main(tmp_path, ["--schema", "schema.json"])

        assert result.returncode == 0
        assert "\r" not in result.stdout
        assert "\r" not in result.stderr

    def test_batch_run_still_completes_normally_with_progress_reporter_active(self, tmp_path):
        """The progress reporter's presence shouldn't affect the actual run outcome."""
        config = make_project(
            tmp_path,
            csv_content="name,age\nAlice,30\n",
            schema_content={"columns": {
                "name": {"type": "string", "required": True},
                "age": {"type": "int", "required": True},
            }},
        )
        result = run_main(tmp_path, ["--schema", "schema.json"])
        assert result.returncode == 0
        conn = sqlite3.connect(config["database_path"])
        rows = conn.execute("SELECT * FROM processed_files").fetchall()
        conn.close()
        assert len(rows) == 1