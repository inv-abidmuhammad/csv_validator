import re
import pandas as pd

def validate_columns(df, schema):
    errors = []
    expected_columns = schema.keys()

    for column in expected_columns:
        if column not in df.columns:
            errors.append(
                {
                    "row": None,
                    "column": column,
                    "value": None,
                    "error": "Column missing from file structure"
                }
            )

    return errors


def validate_required_fields(df, schema):
    errors = []

    for column, rules in schema.items():

        if not rules["required"]:
            continue

        if column not in df.columns:
            continue

        for index, value in df[column].items():

            if pd.isna(value) or str(value).strip() == "":
                errors.append(
                    {
                        "row": index + 2, # note for me: row 2 is the first data row, row 1 is the header
                        "column": column,
                        "value": value,
                        "error": "Required field missing"
                    }
                )

    return errors


def validate_duplicates(df):
    errors = []

    duplicate_rows = df[df.duplicated()]

    for index, row in duplicate_rows.iterrows():
        errors.append(
            {
                "row": index + 2,
                "column": None,
                "value": row.to_dict(),
                "error": "Duplicate record"
            }
        )

    return errors


def is_valid_string(value):
    return isinstance(value, str) and str(value).strip() != ""

def is_valid_int(value):
    try:
        int(value)
        return True
    except (ValueError, TypeError):
        return False
    

def is_valid_float(value):
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False
    

TRUE_VALUES = {
    "true",
    "1",
    "yes"
}

FALSE_VALUES = {
    "false",
    "0",
    "no"
}

def is_valid_boolean(value):
    return (
        str(value).strip().lower()
        in TRUE_VALUES.union(FALSE_VALUES)
    )


def validate_data_types(df, schema):
    errors = []

    for column, rules in schema.items():

        if column not in df.columns:
            continue

        expected_type = rules["type"]

        for index, value in df[column].items():

            if pd.isna(value) or str(value).strip() == "":
                continue

            if expected_type == "int" and not is_valid_int(value):
                errors.append(
                    {
                        "row": index + 2,
                        "column": column,
                        "value": value,
                        "error": "Invalid data type, expected int"
                    }
                )
            elif expected_type == "float" and not is_valid_float(value):
                errors.append(
                    {
                        "row": index + 2,
                        "column": column,
                        "value": value,
                        "error": "Invalid data type, expected float"
                    }
                )
            elif expected_type == "boolean" and not is_valid_boolean(value):
                errors.append(
                    {
                        "row": index + 2,
                        "column": column,
                        "value": value,
                        "error": "Invalid data type, expected boolean"
                    }
                )
    return errors


def validate_patterns(df, schema):
    errors = []

    for column, rules in schema.items():

        if "pattern" not in rules:
            continue

        if column not in df.columns:
            continue

        compiled_pattern = re.compile(rules["pattern"])

        for index, value in df[column].items():

            if pd.isna(value) or str(value).strip() == "":
                continue

            if not compiled_pattern.match(str(value)):
                errors.append(
                    {
                        "row": index + 2,
                        "column": column,
                        "value": value,
                        "error": f"Value does not match required pattern '{rules['pattern']}'"
                    }
                )

    return errors


def validate_ranges(df, schema):
    errors = []

    for column, rules in schema.items():

        has_min = "min" in rules
        has_max = "max" in rules

        if not has_min and not has_max:
            continue

        if column not in df.columns:
            continue

        for index, value in df[column].items():

            if pd.isna(value) or str(value).strip() == "":
                continue

            try:
                numeric_value = float(value)
            except (ValueError, TypeError):
                # Type errors are already reported by validate_data_types.
                # Skip here to avoid duplicate/confusing errors for the same cell.
                continue

            if has_min and numeric_value < rules["min"]:
                errors.append(
                    {
                        "row": index + 2,
                        "column": column,
                        "value": value,
                        "error": f"Value below minimum allowed ({rules['min']})"
                    }
                )
            elif has_max and numeric_value > rules["max"]:
                errors.append(
                    {
                        "row": index + 2,
                        "column": column,
                        "value": value,
                        "error": f"Value above maximum allowed ({rules['max']})"
                    }
                )

    return errors


def validate_uniqueness(df, schema):
    errors = []

    for column, rules in schema.items():

        if not rules.get("unique", False):
            continue

        if column not in df.columns:
            continue

        duplicated_mask = df[column].duplicated(keep=False) & df[column].notna()

        for index, value in df[column][duplicated_mask].items():
            errors.append(
                {
                    "row": index + 2,
                    "column": column,
                    "value": value,
                    "error": f"Duplicate value in column marked as unique"
                }
            )

    return errors


def validate_csv(df, schema):
    all_errors = []
    
    column_errors = validate_columns(df, schema)
    required_field_errors = validate_required_fields(df, schema)
    duplicate_errors = validate_duplicates(df)
    type_errors = validate_data_types(df, schema)
    pattern_errors = validate_patterns(df, schema)
    range_errors = validate_ranges(df, schema)
    uniqueness_errors = validate_uniqueness(df, schema)

    all_errors = (
        column_errors +
        required_field_errors +
        duplicate_errors +
        type_errors +
        pattern_errors +
        range_errors +
        uniqueness_errors
    )

    return all_errors