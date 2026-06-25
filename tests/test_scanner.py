import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from validator.scanner import get_csv_files, get_schema_files


class TestScanner:
    def test_get_csv_files_returns_only_csv(self, tmp_path):
        (tmp_path / "a.csv").write_text("col\n1\n")
        (tmp_path / "b.csv").write_text("col\n2\n")
        (tmp_path / "c.txt").write_text("not a csv")
        result = get_csv_files(tmp_path)
        names = {p.name for p in result}
        assert names == {"a.csv", "b.csv"}

    def test_get_csv_files_empty_dir(self, tmp_path):
        assert get_csv_files(tmp_path) == []

    def test_get_schema_files_returns_only_json(self, tmp_path):
        (tmp_path / "s1.json").write_text("{}")
        (tmp_path / "s2.json").write_text("{}")
        (tmp_path / "readme.txt").write_text("nope")
        result = get_schema_files(tmp_path)
        names = {p.name for p in result}
        assert names == {"s1.json", "s2.json"}

    def test_get_schema_files_empty_dir(self, tmp_path):
        assert get_schema_files(tmp_path) == []