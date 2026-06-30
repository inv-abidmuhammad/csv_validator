import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from validator.validation_engine import (
    is_valid_boolean,
    is_valid_float,
    is_valid_int,
    is_valid_string,
    validate_columns,
    validate_csv,
    validate_data_types,
    validate_duplicates,
    validate_patterns,
    validate_ranges,
    validate_required_fields,
    validate_uniqueness,
)


SAMPLE_SCHEMA = {
    "name": {"type": "string", "required": True},
    "age": {"type": "int", "required": True},
    "score": {"type": "float", "required": False},
    "active": {"type": "boolean", "required": False},
}

SAMPLE_DF = pd.DataFrame(
    {
        "name": ["Alice", "Bob"],
        "age": [30, 25],
        "score": [9.5, 8.0],
        "active": ["true", "false"],
    }
)


class TestIsValidString:
    def test_valid_string(self):
        assert is_valid_string("hello") is True

    def test_empty_string_invalid(self):
        assert is_valid_string("") is False

    def test_whitespace_string_invalid(self):
        assert is_valid_string("   ") is False

    def test_non_string_invalid(self):
        assert is_valid_string(42) is False


class TestIsValidInt:
    def test_valid_int_number(self):
        assert is_valid_int(5) is True

    def test_valid_int_string(self):
        assert is_valid_int("42") is True

    def test_invalid_int_float_string(self):
        assert is_valid_int("3.14") is False

    def test_invalid_int_text(self):
        assert is_valid_int("abc") is False

    def test_invalid_int_none(self):
        assert is_valid_int(None) is False


class TestIsValidFloat:
    def test_valid_float_number(self):
        assert is_valid_float(3.14) is True

    def test_valid_float_string(self):
        assert is_valid_float("3.14") is True

    def test_valid_float_int_string(self):
        assert is_valid_float("42") is True  # ints are valid floats

    def test_invalid_float_text(self):
        assert is_valid_float("abc") is False

    def test_invalid_float_none(self):
        assert is_valid_float(None) is False


class TestIsValidBoolean:
    @pytest.mark.parametrize("val", ["true", "True", "TRUE", "1", "yes", "Yes"])
    def test_truthy_booleans(self, val):
        assert is_valid_boolean(val) is True

    @pytest.mark.parametrize("val", ["false", "False", "FALSE", "0", "no", "No"])
    def test_falsy_booleans(self, val):
        assert is_valid_boolean(val) is True

    def test_invalid_boolean(self):
        assert is_valid_boolean("maybe") is False

    def test_invalid_boolean_empty(self):
        assert is_valid_boolean("") is False


class TestValidateColumns:
    def test_no_errors_when_all_columns_present(self):
        errors = validate_columns(SAMPLE_DF, SAMPLE_SCHEMA)
        assert errors == []

    def test_error_for_missing_column(self):
        df = pd.DataFrame({"name": ["Alice"]})
        errors = validate_columns(df, SAMPLE_SCHEMA)
        missing = {e["column"] for e in errors}
        assert "age" in missing
        assert "score" in missing

    def test_error_message_content(self):
        df = pd.DataFrame({"name": ["Alice"]})
        errors = validate_columns(df, SAMPLE_SCHEMA)
        for e in errors:
            assert "missing" in e["error"].lower()
            assert e["row"] is None


class TestValidateRequiredFields:
    def test_no_errors_for_valid_data(self):
        errors = validate_required_fields(SAMPLE_DF, SAMPLE_SCHEMA)
        assert errors == []

    def test_error_for_null_required_field(self):
        df = pd.DataFrame(
            {"name": ["Alice", None], "age": [30, 25], "score": [9.5, 8.0], "active": ["true", "false"]}
        )
        errors = validate_required_fields(df, SAMPLE_SCHEMA)
        assert len(errors) == 1
        assert errors[0]["column"] == "name"

    def test_error_for_empty_string_required_field(self):
        df = pd.DataFrame(
            {"name": ["Alice", ""], "age": [30, 25], "score": [9.5, 8.0], "active": ["true", "false"]}
        )
        errors = validate_required_fields(df, SAMPLE_SCHEMA)
        assert len(errors) == 1
        assert errors[0]["row"] == 3  # 2nd data row → row 3

    def test_no_error_for_null_optional_field(self):
        df = pd.DataFrame(
            {"name": ["Alice"], "age": [30], "score": [None], "active": [None]}
        )
        errors = validate_required_fields(df, SAMPLE_SCHEMA)
        assert errors == []

    def test_skips_missing_columns(self):
        df = pd.DataFrame({"name": ["Alice"]})
        errors = validate_required_fields(df, SAMPLE_SCHEMA)
        assert all(e["column"] != "age" for e in errors)


class TestValidateDuplicates:
    def test_no_duplicates(self):
        errors = validate_duplicates(SAMPLE_DF)
        assert errors == []

    def test_detects_exact_duplicate(self):
        df = pd.DataFrame({"name": ["Alice", "Alice"], "age": [30, 30]})
        errors = validate_duplicates(df)
        assert len(errors) == 1
        assert "Duplicate" in errors[0]["error"]

    def test_duplicate_row_number_is_correct(self):
        df = pd.DataFrame({"name": ["A", "B", "A"], "age": [1, 2, 1]})
        errors = validate_duplicates(df)
        # 3rd data row (0-indexed row 2) → row 2 + 2 = 4
        assert errors[0]["row"] == 4

    def test_no_false_positive_for_similar_rows(self):
        df = pd.DataFrame({"name": ["Alice", "Alice"], "age": [30, 31]})
        errors = validate_duplicates(df)
        assert errors == []


class TestValidateDataTypes:
    def test_no_errors_for_valid_types(self):
        errors = validate_data_types(SAMPLE_DF, SAMPLE_SCHEMA)
        assert errors == []

    def test_int_error_for_non_integer(self):
        df = pd.DataFrame(
            {"name": ["Alice"], "age": ["thirty"], "score": [9.5], "active": ["true"]}
        )
        errors = validate_data_types(df, SAMPLE_SCHEMA)
        assert any(e["column"] == "age" and "int" in e["error"] for e in errors)

    def test_float_error_for_non_float(self):
        df = pd.DataFrame(
            {"name": ["Alice"], "age": [30], "score": ["bad"], "active": ["true"]}
        )
        errors = validate_data_types(df, SAMPLE_SCHEMA)
        assert any(e["column"] == "score" and "float" in e["error"] for e in errors)

    def test_boolean_error_for_invalid_boolean(self):
        df = pd.DataFrame(
            {"name": ["Alice"], "age": [30], "score": [9.5], "active": ["maybe"]}
        )
        errors = validate_data_types(df, SAMPLE_SCHEMA)
        assert any(e["column"] == "active" and "boolean" in e["error"] for e in errors)

    def test_skips_null_values(self):
        df = pd.DataFrame(
            {"name": ["Alice"], "age": [30], "score": [None], "active": ["true"]}
        )
        errors = validate_data_types(df, SAMPLE_SCHEMA)
        assert not any(e["column"] == "score" for e in errors)

    def test_skips_missing_columns(self):
        df = pd.DataFrame({"name": ["Alice"]})
        errors = validate_data_types(df, SAMPLE_SCHEMA)
        assert isinstance(errors, list)


class TestValidateCsv:
    def test_valid_csv_no_errors(self):
        errors = validate_csv(SAMPLE_DF, SAMPLE_SCHEMA)
        assert errors == []

    def test_aggregates_all_error_types(self):
        df = pd.DataFrame(
            {
                "name": ["Alice", None, "Alice"],
                # 'age' is missing entirely (column error)
                "score": ["bad", 8.0, "bad"],
                "active": ["true", "false", "true"],
            }
        )
        errors = validate_csv(df, SAMPLE_SCHEMA)
        error_types = {e["error"] for e in errors}
        assert any("missing" in t.lower() for t in error_types)

    def test_returns_list(self):
        assert isinstance(validate_csv(SAMPLE_DF, SAMPLE_SCHEMA), list)


class TestValidatePatterns:
    EMAIL_SCHEMA = {
        "email": {"type": "string", "required": True, "pattern": r"^[^@]+@[^@]+\.[^@]+$"},
    }

    def test_no_errors_for_matching_pattern(self):
        df = pd.DataFrame({"email": ["alice@example.com", "bob@example.com"]})
        errors = validate_patterns(df, self.EMAIL_SCHEMA)
        assert errors == []

    def test_error_for_non_matching_pattern(self):
        df = pd.DataFrame({"email": ["not-an-email"]})
        errors = validate_patterns(df, self.EMAIL_SCHEMA)
        assert len(errors) == 1
        assert errors[0]["column"] == "email"
        assert "pattern" in errors[0]["error"].lower()

    def test_skips_columns_without_pattern_rule(self):
        df = pd.DataFrame({"name": ["whatever"]})
        errors = validate_patterns(df, SAMPLE_SCHEMA)
        assert errors == []

    def test_skips_null_values(self):
        df = pd.DataFrame({"email": [None]})
        errors = validate_patterns(df, self.EMAIL_SCHEMA)
        assert errors == []

    def test_skips_missing_columns(self):
        df = pd.DataFrame({"other_col": ["x"]})
        errors = validate_patterns(df, self.EMAIL_SCHEMA)
        assert errors == []

    def test_row_number_correct(self):
        df = pd.DataFrame({"email": ["alice@example.com", "bad-email"]})
        errors = validate_patterns(df, self.EMAIL_SCHEMA)
        assert errors[0]["row"] == 3  # 2nd data row


class TestValidateRanges:
    AGE_SCHEMA = {
        "age": {"type": "int", "required": True, "min": 0, "max": 120},
    }

    def test_no_errors_within_range(self):
        df = pd.DataFrame({"age": [0, 30, 120]})
        errors = validate_ranges(df, self.AGE_SCHEMA)
        assert errors == []

    def test_error_below_minimum(self):
        df = pd.DataFrame({"age": [-5]})
        errors = validate_ranges(df, self.AGE_SCHEMA)
        assert len(errors) == 1
        assert "minimum" in errors[0]["error"].lower()

    def test_error_above_maximum(self):
        df = pd.DataFrame({"age": [150]})
        errors = validate_ranges(df, self.AGE_SCHEMA)
        assert len(errors) == 1
        assert "maximum" in errors[0]["error"].lower()

    def test_skips_columns_without_range_rules(self):
        df = pd.DataFrame({"name": ["Alice"]})
        errors = validate_ranges(df, SAMPLE_SCHEMA)
        assert errors == []

    def test_skips_non_numeric_values(self):
        """Type errors are handled by validate_data_types; ranges should not double-report."""
        df = pd.DataFrame({"age": ["not_a_number"]})
        errors = validate_ranges(df, self.AGE_SCHEMA)
        assert errors == []

    def test_skips_null_values(self):
        df = pd.DataFrame({"age": [None]})
        errors = validate_ranges(df, self.AGE_SCHEMA)
        assert errors == []

    def test_min_only_rule(self):
        schema = {"age": {"type": "int", "required": True, "min": 18}}
        df = pd.DataFrame({"age": [10, 25]})
        errors = validate_ranges(df, schema)
        assert len(errors) == 1
        assert errors[0]["value"] == 10

    def test_max_only_rule(self):
        schema = {"age": {"type": "int", "required": True, "max": 65}}
        df = pd.DataFrame({"age": [70, 25]})
        errors = validate_ranges(df, schema)
        assert len(errors) == 1
        assert errors[0]["value"] == 70


class TestValidateUniqueness:
    UNIQUE_SCHEMA = {
        "employee_id": {"type": "string", "required": True, "unique": True},
    }

    def test_no_errors_for_unique_values(self):
        df = pd.DataFrame({"employee_id": ["E1", "E2", "E3"]})
        errors = validate_uniqueness(df, self.UNIQUE_SCHEMA)
        assert errors == []

    def test_flags_all_duplicate_occurrences(self):
        df = pd.DataFrame({"employee_id": ["E1", "E2", "E1"]})
        errors = validate_uniqueness(df, self.UNIQUE_SCHEMA)
        # Both the original and the repeat should be flagged
        assert len(errors) == 2

    def test_skips_columns_without_unique_rule(self):
        df = pd.DataFrame({"name": ["Alice", "Alice"]})
        errors = validate_uniqueness(df, SAMPLE_SCHEMA)
        assert errors == []

    def test_skips_null_values(self):
        df = pd.DataFrame({"employee_id": [None, None]})
        errors = validate_uniqueness(df, self.UNIQUE_SCHEMA)
        assert errors == []

    def test_skips_missing_columns(self):
        df = pd.DataFrame({"other_col": ["x"]})
        errors = validate_uniqueness(df, self.UNIQUE_SCHEMA)
        assert errors == []