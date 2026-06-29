import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from validator.report_generator import generate_report


class TestGenerateReport:
    def test_creates_report_file(self, tmp_path):
        path = generate_report("data.csv", "schema.json", [], str(tmp_path))
        assert Path(path).exists()

    def test_success_status_when_no_errors(self, tmp_path):
        path = generate_report("data.csv", "schema.json", [], str(tmp_path))
        report = json.loads(Path(path).read_text())
        assert report["status"] == "SUCCESS"
        assert report["error_count"] == 0

    def test_failed_status_when_errors(self, tmp_path):
        errors = [{"row": 2, "column": "name", "value": None, "error": "Required field missing"}]
        path = generate_report("data.csv", "schema.json", errors, str(tmp_path))
        report = json.loads(Path(path).read_text())
        assert report["status"] == "FAILED"
        assert report["error_count"] == 1
        assert report["errors"] == errors

    def test_report_contains_filename(self, tmp_path):
        path = generate_report("data.csv", "schema.json", [], str(tmp_path))
        report = json.loads(Path(path).read_text())
        assert report["file"] == "data.csv"

    def test_report_contains_schema_name(self, tmp_path):
        path = generate_report("data.csv", "schema_v2.json", [], str(tmp_path))
        report = json.loads(Path(path).read_text())
        assert report["schema"] == "schema_v2.json"

    def test_report_filename_contains_file_stem(self, tmp_path):
        path = generate_report("my_data.csv", "schema.json", [], str(tmp_path))
        assert "my_data" in Path(path).name