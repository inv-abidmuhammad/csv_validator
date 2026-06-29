import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from validator.file_utils import generate_file_hash, generate_combined_hash


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


class TestGenerateCombinedHash:
    def test_returns_sha256_hex_string(self):
        h = generate_combined_hash("abc123", "def456")
        assert isinstance(h, str)
        assert len(h) == 64

    def test_same_inputs_same_hash(self):
        assert generate_combined_hash("aaa", "bbb") == generate_combined_hash("aaa", "bbb")

    def test_different_file_hash_different_result(self):
        h1 = generate_combined_hash("file_hash_1", "schema_hash")
        h2 = generate_combined_hash("file_hash_2", "schema_hash")
        assert h1 != h2

    def test_different_schema_hash_different_result(self):
        h1 = generate_combined_hash("file_hash", "schema_hash_1")
        h2 = generate_combined_hash("file_hash", "schema_hash_2")
        assert h1 != h2

    def test_same_file_different_schema_not_skipped(self, tmp_path):
        """Core requirement: same file + different schema = different combined hash."""
        csv = tmp_path / "data.csv"
        schema1 = tmp_path / "schema1.json"
        schema2 = tmp_path / "schema2.json"

        csv.write_text("name,age\nAlice,30\n")
        schema1.write_text('{"columns": {"name": {"type": "string", "required": true}}}')
        schema2.write_text('{"columns": {"age": {"type": "int", "required": true}}}')

        file_hash = generate_file_hash(csv)
        h1 = generate_combined_hash(file_hash, generate_file_hash(schema1))
        h2 = generate_combined_hash(file_hash, generate_file_hash(schema2))

        assert h1 != h2

    def test_same_file_updated_schema_not_skipped(self, tmp_path):
        """Core requirement: same file + edited schema = different combined hash."""
        csv = tmp_path / "data.csv"
        schema = tmp_path / "schema.json"

        csv.write_text("name,age\nAlice,30\n")
        schema.write_text('{"columns": {"name": {"type": "string", "required": true}}}')
        hash_before = generate_combined_hash(generate_file_hash(csv), generate_file_hash(schema))

        schema.write_text('{"columns": {"name": {"type": "string", "required": false}}}')
        hash_after = generate_combined_hash(generate_file_hash(csv), generate_file_hash(schema))

        assert hash_before != hash_after