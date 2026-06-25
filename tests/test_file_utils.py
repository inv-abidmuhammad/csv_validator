import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from validator.file_utils import generate_file_hash


class TestGenerateFileHash:
    def test_returns_sha256_hex_string(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("col1,col2\n1,2\n")
        h = generate_file_hash(f)
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex digest length

    def test_same_content_same_hash(self, tmp_path):
        f1 = tmp_path / "a.csv"
        f2 = tmp_path / "b.csv"
        content = "col1,col2\n1,2\n"
        f1.write_text(content)
        f2.write_text(content)
        assert generate_file_hash(f1) == generate_file_hash(f2)

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.csv"
        f2 = tmp_path / "b.csv"
        f1.write_text("col1\n1\n")
        f2.write_text("col1\n2\n")
        assert generate_file_hash(f1) != generate_file_hash(f2)

    def test_large_file_hashed_correctly(self, tmp_path):
        f = tmp_path / "large.csv"
        f.write_bytes(b"x" * 100_000)
        h = generate_file_hash(f)
        assert len(h) == 64