import csv
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from validator.report_generator import (
    generate_csv_report,
    generate_html_report,
    generate_report,
    generate_summary_stats,
)


SAMPLE_DF = pd.DataFrame({"name": ["Alice", "Bob", "Carol"]})


class TestGenerateReport:
    def test_creates_report_file(self, tmp_path):
        path = generate_report("data.csv", "schema.json", SAMPLE_DF, [], str(tmp_path))
        assert Path(path).exists()

    def test_success_status_when_no_errors(self, tmp_path):
        path = generate_report("data.csv", "schema.json", SAMPLE_DF, [], str(tmp_path))
        report = json.loads(Path(path).read_text())
        assert report["status"] == "SUCCESS"
        assert report["error_count"] == 0

    def test_failed_status_when_errors(self, tmp_path):
        errors = [{"row": 2, "column": "name", "value": None, "error": "Required field missing"}]
        path = generate_report("data.csv", "schema.json", SAMPLE_DF, errors, str(tmp_path))
        report = json.loads(Path(path).read_text())
        assert report["status"] == "FAILED"
        assert report["error_count"] == 1
        assert report["errors"] == errors

    def test_report_contains_filename(self, tmp_path):
        path = generate_report("data.csv", "schema.json", SAMPLE_DF, [], str(tmp_path))
        report = json.loads(Path(path).read_text())
        assert report["file"] == "data.csv"

    def test_report_contains_schema_name(self, tmp_path):
        path = generate_report("data.csv", "schema_v2.json", SAMPLE_DF, [], str(tmp_path))
        report = json.loads(Path(path).read_text())
        assert report["schema"] == "schema_v2.json"

    def test_report_filename_contains_file_stem(self, tmp_path):
        path = generate_report("my_data.csv", "schema.json", SAMPLE_DF, [], str(tmp_path))
        assert "my_data" in Path(path).name

    def test_report_contains_summary(self, tmp_path):
        path = generate_report("data.csv", "schema.json", SAMPLE_DF, [], str(tmp_path))
        report = json.loads(Path(path).read_text())
        assert "summary" in report
        assert report["summary"]["rows_processed"] == 3
        assert report["summary"]["rows_passed"] == 3
        assert report["summary"]["rows_failed"] == 0

    def test_no_extra_formats_by_default(self, tmp_path):
        generate_report("data.csv", "schema.json", SAMPLE_DF, [], str(tmp_path))
        all_files = list(tmp_path.glob("*"))
        assert len(all_files) == 1  # only the .json
        assert all_files[0].suffix == ".json"

    def test_formats_csv_creates_csv_file(self, tmp_path):
        generate_report("data.csv", "schema.json", SAMPLE_DF, [], str(tmp_path), formats=["csv"])
        csv_files = list(tmp_path.glob("*.csv"))
        assert len(csv_files) == 1

    def test_formats_html_creates_html_file(self, tmp_path):
        generate_report("data.csv", "schema.json", SAMPLE_DF, [], str(tmp_path), formats=["html"])
        html_files = list(tmp_path.glob("*.html"))
        assert len(html_files) == 1

    def test_formats_csv_and_html_creates_both(self, tmp_path):
        generate_report(
            "data.csv", "schema.json", SAMPLE_DF, [], str(tmp_path), formats=["csv", "html"]
        )
        assert len(list(tmp_path.glob("*.csv"))) == 1
        assert len(list(tmp_path.glob("*.html"))) == 1
        assert len(list(tmp_path.glob("*.json"))) == 1

    def test_json_always_returned_regardless_of_formats(self, tmp_path):
        path = generate_report(
            "data.csv", "schema.json", SAMPLE_DF, [], str(tmp_path), formats=["csv", "html"]
        )
        assert path.suffix == ".json"
        assert path.exists()

    def test_csv_and_html_share_stem_with_json(self, tmp_path):
        json_path = generate_report(
            "data.csv", "schema.json", SAMPLE_DF, [], str(tmp_path), formats=["csv", "html"]
        )
        csv_path = next(tmp_path.glob("*.csv"))
        html_path = next(tmp_path.glob("*.html"))
        assert json_path.stem == csv_path.stem == html_path.stem


class TestGenerateSummaryStats:
    def test_no_errors_all_rows_pass(self):
        stats = generate_summary_stats(SAMPLE_DF, [])
        assert stats["rows_processed"] == 3
        assert stats["rows_passed"] == 3
        assert stats["rows_failed"] == 0
        assert stats["total_errors"] == 0
        assert stats["duplicates_found"] == 0

    def test_counts_rows_processed_from_df_length(self):
        df = pd.DataFrame({"col": range(10)})
        stats = generate_summary_stats(df, [])
        assert stats["rows_processed"] == 10

    def test_failed_rows_counted_by_unique_row_number(self):
        # Two errors on the same row should only count as one failed row
        errors = [
            {"row": 2, "column": "name", "value": None, "error": "Required field missing"},
            {"row": 2, "column": "age", "value": "x", "error": "Invalid data type, expected int"},
        ]
        stats = generate_summary_stats(SAMPLE_DF, errors)
        assert stats["rows_failed"] == 1
        assert stats["rows_passed"] == 2  # 3 total - 1 failed
        assert stats["total_errors"] == 2  # but both errors still counted

    def test_multiple_distinct_failed_rows(self):
        errors = [
            {"row": 2, "column": "name", "value": None, "error": "Required field missing"},
            {"row": 3, "column": "name", "value": None, "error": "Required field missing"},
        ]
        stats = generate_summary_stats(SAMPLE_DF, errors)
        assert stats["rows_failed"] == 2
        assert stats["rows_passed"] == 1

    def test_column_level_errors_excluded_from_row_counts(self):
        """Errors with row=None (e.g. missing column) shouldn't count as a failed row."""
        errors = [
            {"row": None, "column": "age", "value": None, "error": "Column missing from file structure"},
        ]
        stats = generate_summary_stats(SAMPLE_DF, errors)
        assert stats["rows_failed"] == 0
        assert stats["rows_passed"] == 3
        assert stats["total_errors"] == 1

    def test_duplicates_found_counts_duplicate_record_errors(self):
        errors = [
            {"row": 2, "column": None, "value": {}, "error": "Duplicate record"},
            {"row": 3, "column": None, "value": {}, "error": "Duplicate record"},
        ]
        stats = generate_summary_stats(SAMPLE_DF, errors)
        assert stats["duplicates_found"] == 2

    def test_duplicates_found_zero_when_no_duplicate_errors(self):
        errors = [
            {"row": 2, "column": "name", "value": None, "error": "Required field missing"},
        ]
        stats = generate_summary_stats(SAMPLE_DF, errors)
        assert stats["duplicates_found"] == 0

    def test_errors_by_type_groups_correctly(self):
        errors = [
            {"row": 2, "column": "name", "value": None, "error": "Required field missing"},
            {"row": 3, "column": "name", "value": None, "error": "Required field missing"},
            {"row": 4, "column": "age", "value": "x", "error": "Invalid data type, expected int"},
        ]
        stats = generate_summary_stats(SAMPLE_DF, errors)
        assert stats["errors_by_type"]["Required field missing"] == 2
        assert stats["errors_by_type"]["Invalid data type, expected int"] == 1

    def test_empty_dataframe(self):
        empty_df = pd.DataFrame({"name": []})
        stats = generate_summary_stats(empty_df, [])
        assert stats["rows_processed"] == 0
        assert stats["rows_passed"] == 0
        assert stats["rows_failed"] == 0


def _build_sample_report(errors=None):
    if errors is None:
        errors = []
    return {
        "file": "data.csv",
        "schema": "schema.json",
        "status": "FAILED" if errors else "SUCCESS",
        "error_count": len(errors),
        "summary": generate_summary_stats(SAMPLE_DF, errors),
        "errors": errors,
    }


class TestGenerateCsvReport:
    def test_creates_csv_file(self, tmp_path):
        report = _build_sample_report()
        path = generate_csv_report(report, str(tmp_path), "report_stem")
        assert path.exists()
        assert path.suffix == ".csv"

    def test_header_row_present(self, tmp_path):
        report = _build_sample_report()
        path = generate_csv_report(report, str(tmp_path), "report_stem")
        with open(path) as f:
            reader = csv.reader(f)
            header = next(reader)
        assert header == ["file", "schema", "status", "row", "column", "value", "error"]

    def test_no_errors_writes_single_clean_row(self, tmp_path):
        report = _build_sample_report()
        path = generate_csv_report(report, str(tmp_path), "report_stem")
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["status"] == "SUCCESS"
        assert rows[0]["error"] == ""

    def test_one_row_per_error(self, tmp_path):
        errors = [
            {"row": 2, "column": "name", "value": None, "error": "Required field missing"},
            {"row": 3, "column": "age", "value": "x", "error": "Invalid data type, expected int"},
        ]
        report = _build_sample_report(errors)
        path = generate_csv_report(report, str(tmp_path), "report_stem")
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["column"] == "name"
        assert rows[1]["column"] == "age"

    def test_column_level_error_handles_none_row(self, tmp_path):
        errors = [
            {"row": None, "column": "age", "value": None, "error": "Column missing from file structure"},
        ]
        report = _build_sample_report(errors)
        path = generate_csv_report(report, str(tmp_path), "report_stem")
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert rows[0]["row"] == ""

    def test_file_and_schema_repeated_on_every_row(self, tmp_path):
        errors = [
            {"row": 2, "column": "name", "value": None, "error": "Required field missing"},
            {"row": 3, "column": "age", "value": "x", "error": "Invalid data type, expected int"},
        ]
        report = _build_sample_report(errors)
        path = generate_csv_report(report, str(tmp_path), "report_stem")
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert all(row["file"] == "data.csv" for row in rows)
        assert all(row["schema"] == "schema.json" for row in rows)


class TestGenerateHtmlReport:
    def test_creates_html_file(self, tmp_path):
        report = _build_sample_report()
        path = generate_html_report(report, str(tmp_path), "report_stem")
        assert path.exists()
        assert path.suffix == ".html"

    def test_contains_filename(self, tmp_path):
        report = _build_sample_report()
        path = generate_html_report(report, str(tmp_path), "report_stem")
        content = path.read_text()
        assert "data.csv" in content

    def test_contains_status(self, tmp_path):
        report = _build_sample_report()
        path = generate_html_report(report, str(tmp_path), "report_stem")
        content = path.read_text()
        assert "SUCCESS" in content

    def test_no_errors_shows_no_errors_message(self, tmp_path):
        report = _build_sample_report()
        path = generate_html_report(report, str(tmp_path), "report_stem")
        content = path.read_text()
        assert "No errors found" in content

    def test_errors_appear_in_table(self, tmp_path):
        errors = [
            {"row": 2, "column": "name", "value": None, "error": "Required field missing"},
        ]
        report = _build_sample_report(errors)
        path = generate_html_report(report, str(tmp_path), "report_stem")
        content = path.read_text()
        assert "Required field missing" in content
        assert "<td>name</td>" in content

    def test_html_escapes_special_characters_in_values(self, tmp_path):
        """Error values containing HTML-significant characters must not break the page."""
        errors = [
            {"row": 2, "column": "name", "value": "<script>alert('x')</script>", "error": "Required field missing"},
        ]
        report = _build_sample_report(errors)
        path = generate_html_report(report, str(tmp_path), "report_stem")
        content = path.read_text()
        assert "<script>alert" not in content
        assert "&lt;script&gt;" in content

    def test_summary_stats_appear_in_table(self, tmp_path):
        errors = [
            {"row": 2, "column": "name", "value": None, "error": "Required field missing"},
        ]
        report = _build_sample_report(errors)
        path = generate_html_report(report, str(tmp_path), "report_stem")
        content = path.read_text()
        assert "rows_processed" in content
        assert "rows_failed" in content

    def test_valid_html_structure(self, tmp_path):
        report = _build_sample_report()
        path = generate_html_report(report, str(tmp_path), "report_stem")
        content = path.read_text()
        assert content.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in content