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