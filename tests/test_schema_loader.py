import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from validator.schema_loader import load_schema, validate_schema_structure


SAMPLE_SCHEMA = {
    "name": {"type": "string", "required": True},
    "age": {"type": "int", "required": True},
    "score": {"type": "float", "required": False},
    "active": {"type": "boolean", "required": False},
}


class TestValidateSchemaStructure:
    def test_valid_schema_returns_columns(self):
        result = validate_schema_structure({"columns": SAMPLE_SCHEMA})
        assert result == SAMPLE_SCHEMA

    def test_missing_columns_key_raises(self):
        with pytest.raises(ValueError, match="'columns'"):
            validate_schema_structure({"fields": {}})

    def test_column_missing_type_raises(self):
        schema = {"columns": {"col": {"required": True}}}
        with pytest.raises(ValueError, match="type"):
            validate_schema_structure(schema)

    def test_column_missing_required_raises(self):
        schema = {"columns": {"col": {"type": "string"}}}
        with pytest.raises(ValueError, match="required"):
            validate_schema_structure(schema)

    def test_unsupported_type_raises(self):
        schema = {"columns": {"col": {"type": "datetime", "required": True}}}
        with pytest.raises(ValueError, match="Unsupported type"):
            validate_schema_structure(schema)

    def test_invalid_required_value_raises(self):
        schema = {"columns": {"col": {"type": "string", "required": "yes"}}}
        with pytest.raises(ValueError, match="invalid 'required'"):
            validate_schema_structure(schema)

    def test_all_supported_types_accepted(self):
        for t in ("string", "int", "float", "boolean"):
            schema = {"columns": {"col": {"type": t, "required": False}}}
            result = validate_schema_structure(schema)
            assert result["col"]["type"] == t

    # --- pattern ---
    def test_valid_pattern_accepted(self):
        schema = {"columns": {"col": {"type": "string", "required": True, "pattern": r"^\d+$"}}}
        result = validate_schema_structure(schema)
        assert result["col"]["pattern"] == r"^\d+$"

    def test_non_string_pattern_raises(self):
        schema = {"columns": {"col": {"type": "string", "required": True, "pattern": 123}}}
        with pytest.raises(ValueError, match="pattern"):
            validate_schema_structure(schema)

    def test_invalid_regex_pattern_raises(self):
        schema = {"columns": {"col": {"type": "string", "required": True, "pattern": "[unclosed"}}}
        with pytest.raises(ValueError, match="invalid regex"):
            validate_schema_structure(schema)

    # --- min / max ---
    def test_valid_min_max_accepted(self):
        schema = {"columns": {"col": {"type": "int", "required": True, "min": 0, "max": 100}}}
        result = validate_schema_structure(schema)
        assert result["col"]["min"] == 0
        assert result["col"]["max"] == 100

    def test_non_numeric_min_raises(self):
        schema = {"columns": {"col": {"type": "int", "required": True, "min": "zero"}}}
        with pytest.raises(ValueError, match="'min'"):
            validate_schema_structure(schema)

    def test_non_numeric_max_raises(self):
        schema = {"columns": {"col": {"type": "int", "required": True, "max": "hundred"}}}
        with pytest.raises(ValueError, match="'max'"):
            validate_schema_structure(schema)

    def test_min_greater_than_max_raises(self):
        schema = {"columns": {"col": {"type": "int", "required": True, "min": 100, "max": 0}}}
        with pytest.raises(ValueError, match="greater than"):
            validate_schema_structure(schema)

    # --- unique ---
    def test_valid_unique_accepted(self):
        schema = {"columns": {"col": {"type": "string", "required": True, "unique": True}}}
        result = validate_schema_structure(schema)
        assert result["col"]["unique"] is True

    def test_non_boolean_unique_raises(self):
        schema = {"columns": {"col": {"type": "string", "required": True, "unique": "yes"}}}
        with pytest.raises(ValueError, match="'unique'"):
            validate_schema_structure(schema)


class TestLoadSchema:
    def test_loads_valid_schema_file(self, tmp_path):
        path = tmp_path / "schema.json"
        path.write_text(json.dumps({"columns": SAMPLE_SCHEMA}))
        result = load_schema(path)
        assert result == SAMPLE_SCHEMA

    def test_raises_on_invalid_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{ this is not json }")
        with pytest.raises(ValueError, match="invalid JSON"):
            load_schema(bad)

    def test_raises_on_missing_columns_key(self, tmp_path):
        f = tmp_path / "s.json"
        f.write_text(json.dumps({"not_columns": {}}))
        with pytest.raises(ValueError, match="missing 'columns' key"):
            load_schema(f)